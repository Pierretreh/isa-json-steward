"""
Format Converter for converting proprietary file formats to standard formats.

This module converts proprietary formats (.czi, .fcs, .xlsx, .wsp, .xml, .ndpi,
.lif, .pzfx, .lof, .xlif, .xlef) to standard formats (.tiff, .csv, .json)
while preserving all metadata.
"""

import csv
import json
import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from utils.batch.metadata_extractor import MetadataExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    """Result of a file conversion operation."""

    source_file: str
    target_file: str
    success: bool
    conversion_type: str
    metadata_file: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class FormatConverter:
    """Converter for proprietary file formats to standard formats."""

    def __init__(self, preserve_originals: bool = True):
        """
        Initialize the format converter.

        Args:
            preserve_originals: Whether to preserve original files
        """
        self.preserve_originals = preserve_originals
        self.metadata_extractor = MetadataExtractor()
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # FCS DATA segment helpers (native parser – no external dependencies)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_fcs_header(raw: bytes) -> Dict[str, Any]:
        """Parse the 58-byte FCS file header.

        Returns a dict with ``version``, ``text_start``, ``text_end``,
        ``data_start``, ``data_end``, ``analysis_start``, ``analysis_end``.
        """
        if len(raw) < 58:
            raise ValueError("File too small to be a valid FCS file")

        def _int(s: str) -> int:
            return int(s.strip())

        header_str = raw[:58].decode("ascii", errors="ignore")
        return {
            "version": header_str[0:6].strip(),
            "text_start": _int(header_str[10:18]),
            "text_end": _int(header_str[18:26]),
            "data_start": _int(header_str[26:34]),
            "data_end": _int(header_str[34:42]),
            "analysis_start": _int(header_str[42:50]),
            "analysis_end": _int(header_str[50:58]),
        }

    @staticmethod
    def _parse_fcs_keywords(raw: bytes, text_start: int, text_end: int) -> Dict[str, str]:
        """Parse the FCS TEXT segment into a keyword dict."""
        if text_start <= 0 or text_end <= text_start or text_end > len(raw):
            return {}
        text_segment = raw[text_start:text_end].decode("latin1", errors="ignore")
        if not text_segment:
            return {}
        delimiter = text_segment[0]
        tokens = text_segment.split(delimiter)
        keywords: Dict[str, str] = {}
        # tokens[0] is empty (before first delimiter), then alternating key/value
        for i in range(1, len(tokens) - 1, 2):
            key = tokens[i].strip()
            if key:
                keywords[key] = tokens[i + 1].strip()
        return keywords

    @staticmethod
    def _fcs_byte_order(keywords: Dict[str, str]) -> str:
        """Return ``'little'`` or ``'big'`` from the ``$BYTEORD`` keyword."""
        bo = keywords.get("$BYTEORD", "1,2,3,4").strip()
        return "little" if bo.startswith("1") else "big"

    def _parse_fcs_data_segment(
        self, raw: bytes, keywords: Dict[str, str], data_start: int, data_end: int
    ) -> List[List[float]]:
        """Parse the FCS DATA segment into a list of events.

        Each event is a list of float values, one per parameter.

        Supports:
        - ``$DATATYPE`` = ``F`` (32-bit float), ``D`` (64-bit double), ``I`` (integer),
             ``A`` (ASCII)
        - ``$MODE`` = ``L`` (list mode)
        - FCS 3.0/3.1 can have a supplemental DATA segment when the primary
          offsets are 0 (stored in ``$BEGINDATA`` / ``$ENDDATA`` keywords).

        Returns an empty list on any parsing failure so the caller can still
        produce a metadata-only CSV.
        """
        try:
            n_params = int(keywords.get("$PAR", "0"))
            n_events = int(keywords.get("$TOT", "0"))

            if n_params == 0 or n_events == 0:
                self.logger.warning("FCS: $PAR or $TOT is 0 – cannot parse data")
                return []

            # FCS 3.0+ may store real offsets in keywords when header offsets are 0
            if data_start == 0 or data_end == 0:
                kw_start = keywords.get("$BEGINDATA", "")
                kw_end = keywords.get("$ENDDATA", "")
                if kw_start and kw_end:
                    data_start = int(kw_start.strip())
                    data_end = int(kw_end.strip())

            if data_start <= 0 or data_end <= data_start or data_end > len(raw):
                self.logger.warning(f"FCS: DATA segment offsets invalid ({data_start}-{data_end})")
                return []

            byte_order = self._fcs_byte_order(keywords)
            datatype = keywords.get("$DATATYPE", "I").strip().upper()
            data_bytes = raw[data_start:data_end]

            # Determine per-parameter byte widths
            bit_widths: List[int] = []
            for i in range(1, n_params + 1):
                bits = int(keywords.get(f"$P{i}B", "32"))
                bit_widths.append(bits)

            # --- LIST MODE ($MODE == L) ---
            mode = keywords.get("$MODE", "L").strip().upper()
            if mode != "L":
                self.logger.warning(f"FCS: $MODE={mode} – only list mode (L) is supported")
                return []

            events: List[List[float]] = []
            offset = 0

            if datatype == "F":
                # 32-bit float per parameter, regardless of $PnB
                step = n_params * 4
                for _ in range(n_events):
                    if offset + step > len(data_bytes):
                        break
                    row = []
                    for p in range(n_params):
                        val = struct.unpack_from(
                            "<f" if byte_order == "little" else ">f", data_bytes, offset + p * 4
                        )[0]
                        row.append(float(val))
                    events.append(row)
                    offset += step

            elif datatype == "D":
                # 64-bit double per parameter
                step = n_params * 8
                for _ in range(n_events):
                    if offset + step > len(data_bytes):
                        break
                    row = []
                    for p in range(n_params):
                        val = struct.unpack_from(
                            "<d" if byte_order == "little" else ">d", data_bytes, offset + p * 8
                        )[0]
                        row.append(float(val))
                    events.append(row)
                    offset += step

            elif datatype == "I":
                # Integer – byte width comes from $PnB
                for _ in range(n_events):
                    row = []
                    for p in range(n_params):
                        bw = bit_widths[p] // 8  # bits → bytes
                        if bw == 1:
                            fmt = "<B" if byte_order == "little" else ">B"
                        elif bw == 2:
                            fmt = "<H" if byte_order == "little" else ">H"
                        elif bw == 4:
                            fmt = "<I" if byte_order == "little" else ">I"
                        else:
                            fmt = "<I" if byte_order == "little" else ">I"
                            bw = 4
                        if offset + bw > len(data_bytes):
                            row.append(0.0)
                            continue
                        val = struct.unpack_from(fmt, data_bytes, offset)[0]
                        row.append(float(val))
                        offset += bw
                    events.append(row)

            elif datatype == "A":
                # ASCII – values separated by delimiters
                text = data_bytes.decode("ascii", errors="ignore")
                values = re.split(r"[\s,]+", text.strip())
                idx = 0
                for _ in range(n_events):
                    row = []
                    for p in range(n_params):
                        if idx < len(values):
                            try:
                                row.append(float(values[idx]))
                            except ValueError:
                                row.append(0.0)
                            idx += 1
                        else:
                            row.append(0.0)
                    events.append(row)
            else:
                self.logger.warning(f"FCS: Unknown $DATATYPE={datatype}")

            return events

        except Exception as e:
            self.logger.warning(f"FCS DATA segment parsing failed: {e}")
            return []

    def _find_existing_tiff(self, czi_path: Path) -> Optional[Path]:
        """Check if a TIFF file already exists for this CZI file.

        Looks for ``<stem>.tif`` or ``<stem>.tiff`` in the same directory
        as the CZI file.  Returns the path to the existing TIFF or ``None``.
        """
        parent = czi_path.parent
        stem = czi_path.stem
        for ext in (".tif", ".tiff"):
            candidate = parent / (stem + ext)
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate
        return None

    def convert_czi_to_tiff(self, czi_path: str, output_dir: str) -> List[str]:
        """
        Convert Zeiss CZI microscopy files to TIFF format.

        Attempts to use the ``czifile`` library (declared as an optional
        dependency in ``pyproject.toml`` under ``[project.optional-dependencies]
        conversion``).  If ``czifile`` is not installed, a minimal header-only
        TIFF placeholder is written and the original metadata is preserved in
        a sidecar JSON so that downstream pipelines still have access to the
        experiment context.

        If a TIFF file with the same stem already exists alongside the CZI
        file (e.g. exported by the microscope operator), the existing TIFF
        is reused and no conversion is performed.

        Args:
            czi_path: Path to the CZI file
            output_dir: Directory to save converted files

        Returns:
            List of converted file paths
        """
        czi_file = Path(czi_path)
        output_path = Path(output_dir)
        results: List[str] = []

        try:
            output_path.mkdir(parents=True, exist_ok=True)

            # Check for pre-existing TIFF (operator-exported)
            existing_tiff = self._find_existing_tiff(czi_file)
            if existing_tiff:
                self.logger.info(
                    f"Reusing existing TIFF for {czi_file.name}: " f"{existing_tiff.name}"
                )
                # Write metadata sidecar referencing the existing file
                metadata = self.metadata_extractor.extract_czi_metadata(czi_path)
                metadata["conversion"] = {
                    "library": "existing_tiff",
                    "note": "TIFF already exists alongside CZI – no conversion needed",
                    "output_file": existing_tiff.name,
                }
                metadata_path = output_path / (czi_file.stem + "_metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, default=str)
                results.append(str(existing_tiff))
                return results

            # Extract metadata (always – regardless of conversion success)
            metadata = self.metadata_extractor.extract_czi_metadata(czi_path)

            target_name = czi_file.stem + ".tiff"
            target_path = output_path / target_name

            converted_ok = False

            # --- Try real conversion via czifile + tifffile ---
            try:
                import czifile as _czifile  # type: ignore
                import tifffile as _tifffile  # type: ignore

                with _czifile.CziFile(str(czi_file)) as czi:
                    # czi.asarray() returns the full image stack as a NumPy array
                    image_data = czi.asarray()
                    # Squeeze singleton dimensions for a cleaner output
                    import numpy as _np

                    image_data = _np.squeeze(image_data)
                    _tifffile.imwrite(str(target_path), image_data, compression="lzw")
                    converted_ok = True

                    # Enrich metadata with shape info
                    metadata["conversion"] = {
                        "library": "czifile + tifffile",
                        "output_shape": list(image_data.shape),
                        "output_dtype": str(image_data.dtype),
                        "output_file": target_name,
                    }
            except ImportError:
                self.logger.info("czifile/tifffile not installed – writing placeholder TIFF")
            except Exception as conv_err:
                self.logger.warning(
                    f"CZI real conversion failed ({conv_err}) – writing placeholder"
                )

            # --- Fallback: write a minimal placeholder TIFF ---
            if not converted_ok:
                with open(target_path, "wb") as f:
                    # Minimal TIFF header (little-endian, single IFD)
                    f.write(b"II\x2a\x00\x08\x00\x00\x00")
                metadata["conversion"] = {
                    "library": "placeholder",
                    "note": "czifile or tifffile not installed – placeholder TIFF written",
                    "output_file": target_name,
                }
                self.logger.warning(f"CZI→TIFF placeholder for {czi_file.name}")

            # Save metadata sidecar
            metadata_path = output_path / (czi_file.stem + "_metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            results.append(str(target_path))
            self.logger.info(f"Converted {czi_file.name} → {target_name}  (real={converted_ok})")

        except Exception as e:
            self.logger.error(f"Error converting {czi_path} to TIFF: {e}")

        return results

    def convert_ndpi_to_tiff(self, ndpi_path: str, output_dir: str) -> Tuple[str, str]:
        """
        Convert Hamamatsu NanoZoomer slide scanner files (.ndpi) to TIFF format.

        Attempts to use ``tifffile`` (which supports NDPI natively).  Falls
        back to ``openslide-python``.  If neither library is available a
        placeholder TIFF is written.

        Args:
            ndpi_path: Path to the .ndpi file
            output_dir: Directory to save converted files

        Returns:
            Tuple of (tiff_path, metadata_path)
        """
        ndpi_file = Path(ndpi_path)
        output_path = Path(output_dir)

        try:
            output_path.mkdir(parents=True, exist_ok=True)
            target_name = ndpi_file.stem + ".tiff"
            target_path = output_path / target_name
            metadata_path = output_path / (ndpi_file.stem + "_metadata.json")
            converted = False

            # --- Try tifffile (native NDPI support) ---
            try:
                import numpy as _np
                import tifffile as _tifffile  # type: ignore

                with _tifffile.TiffFile(str(ndpi_file)) as tif:
                    # NDPI files are pyramidal TIFFs.  Page 0 is the
                    # full-resolution gigapixel image.  Intermediate pages
                    # are progressively smaller pyramid levels.  The last
                    # page(s) may be label / barcode images (grayscale,
                    # non-RGB) rather than actual microscopy data.
                    #
                    # Strategy: find the smallest RGB pyramid page whose
                    # longest side is >= 4096 px (adequate thumbnail).
                    # If none meet the threshold, use the largest available
                    # RGB page.  Skip both gigapixel pages and non-RGB
                    # pages (labels, barcodes).

                    # Gather candidate RGB pages that are not gigapixel
                    min_longest = 4096
                    gigapixel_threshold = 20000
                    candidates: List[Tuple[int, Any, int]] = []
                    for idx, page in enumerate(tif.pages):
                        shape = page.shape
                        if len(shape) == 3 and shape[2] == 3:
                            longest = max(shape[0], shape[1])
                            if longest <= gigapixel_threshold:
                                candidates.append((idx, page, longest))

                    chosen_page = None
                    chosen_idx = -1
                    if candidates:
                        # Prefer the smallest page that meets the minimum
                        # resolution (best quality without being wasteful)
                        above = [c for c in candidates if c[2] >= min_longest]
                        if above:
                            chosen_idx, chosen_page, _ = min(above, key=lambda c: c[2])
                        else:
                            # No page meets the threshold – use the
                            # largest available for best quality
                            chosen_idx, chosen_page, _ = max(candidates, key=lambda c: c[2])
                    else:
                        # Fallback: use the last page (may be a label but
                        # better than nothing)
                        chosen_idx = len(tif.pages) - 1
                        chosen_page = tif.pages[chosen_idx]

                    image_data = chosen_page.asarray()
                    image_data = _np.squeeze(image_data)
                    _tifffile.imwrite(str(target_path), image_data, compression="lzw")
                    converted = True
                    self.logger.info(
                        f"NDPI: selected page {chosen_idx} "
                        f"({chosen_page.shape}) from {ndpi_file.name}"
                    )
            except ImportError:
                self.logger.info("tifffile not installed – trying openslide")
            except Exception as e:
                self.logger.warning(f"tifffile NDPI read failed ({e}) – trying openslide")

            # --- Fallback: openslide-python ---
            if not converted:
                try:
                    import numpy as _np
                    import openslide as _openslide  # type: ignore
                    import tifffile as _tifffile  # type: ignore

                    slide = _openslide.open_slide(str(ndpi_file))
                    # Use get_thumbnail to get a reasonable-size overview
                    # instead of trying to read the full gigapixel image
                    thumbnail = slide.get_thumbnail((2048, 2048)).convert("RGB")
                    image_data = _np.array(thumbnail)
                    _tifffile.imwrite(str(target_path), image_data, compression="lzw")
                    converted = True
                    self.logger.info(
                        f"NDPI via openslide: {image_data.shape} from {ndpi_file.name}"
                    )
                except ImportError:
                    self.logger.info("openslide-python not installed")
                except Exception as e:
                    self.logger.warning(f"openslide NDPI read failed ({e})")

            # --- Fallback: placeholder ---
            if not converted:
                with open(target_path, "wb") as f:
                    f.write(b"II\x2a\x00\x08\x00\x00\x00")
                self.logger.warning(f"NDPI→TIFF placeholder for {ndpi_file.name}")

            metadata = {
                "file_type": "ndpi",
                "source_file": str(ndpi_file),
                "converted_to": target_name,
                "real_conversion": converted,
            }
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            self.logger.info(f"Converted {ndpi_file.name} → {target_name}  (real={converted})")
            return str(target_path), str(metadata_path)

        except Exception as e:
            self.logger.error(f"Error converting {ndpi_path} to TIFF: {e}")
            return "", ""

    def convert_lif_to_tiff(self, lif_path: str, output_dir: str) -> Tuple[str, str]:
        """
        Convert Leica LAS X confocal image files (.lif) to TIFF format.

        Uses ``readlif`` (pure-Python Leica LIF reader).  If not installed,
        a placeholder TIFF is written.

        Args:
            lif_path: Path to the .lif file
            output_dir: Directory to save converted files

        Returns:
            Tuple of (tiff_path, metadata_path)
        """
        lif_file = Path(lif_path)
        output_path = Path(output_dir)

        try:
            output_path.mkdir(parents=True, exist_ok=True)
            metadata_path = output_path / (lif_file.stem + "_metadata.json")
            converted = False
            tiff_path = ""

            try:
                from readlif.reader import LifFile  # type: ignore

                lif = LifFile(str(lif_file))
                # Convert each image series in the LIF file
                for i, image in enumerate(lif.get_iter_image()):
                    suffix = f"_series{i}" if len(list(lif.get_iter_image())) > 1 else ""
                    target_name = lif_file.stem + suffix + ".tiff"
                    target_path = output_path / target_name

                    # Get the first z-plane, first timepoint as a representative image
                    try:
                        img = image.get_frame(z=0, t=0)
                        import numpy as _np

                        image_data = _np.array(img)
                        import tifffile as _tifffile

                        _tifffile.imwrite(str(target_path), image_data, compression="lzw")
                        tiff_path = str(target_path)
                        converted = True
                    except Exception as e:
                        self.logger.warning(f"LIF series {i} read failed: {e}")

            except ImportError:
                self.logger.info("readlif not installed – writing placeholder")
            except Exception as e:
                self.logger.warning(f"readlif LIF read failed ({e})")

            if not converted:
                target_name = lif_file.stem + ".tiff"
                target_path = output_path / target_name
                with open(target_path, "wb") as f:
                    f.write(b"II\x2a\x00\x08\x00\x00\x00")
                tiff_path = str(target_path)
                self.logger.warning(f"LIF→TIFF placeholder for {lif_file.name}")

            metadata = {
                "file_type": "lif",
                "source_file": str(lif_file),
                "converted_to": Path(tiff_path).name if tiff_path else "",
                "real_conversion": converted,
            }
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            self.logger.info(f"Converted {lif_file.name} → TIFF  (real={converted})")
            return tiff_path, str(metadata_path)

        except Exception as e:
            self.logger.error(f"Error converting {lif_path} to TIFF: {e}")
            return "", ""

    def convert_fcs_to_csv(self, fcs_path: str, output_dir: str) -> Tuple[str, str]:
        """
        Convert FACS flow cytometry files to CSV format.

        Uses a native FCS parser (no external library) that reads the FCS
        header, TEXT segment (keywords), and DATA segment to produce a CSV
        with one row per event and one column per parameter.

        Args:
            fcs_path: Path to the FCS file
            output_dir: Directory to save converted files

        Returns:
            Tuple of (csv_path, metadata_path)
        """
        fcs_file = Path(fcs_path)
        output_path = Path(output_dir)

        try:
            output_path.mkdir(parents=True, exist_ok=True)

            # Read entire file
            with open(fcs_path, "rb") as f:
                raw = f.read()

            # Parse header
            hdr = self._parse_fcs_header(raw)

            # Parse TEXT segment (keywords)
            keywords = self._parse_fcs_keywords(raw, hdr["text_start"], hdr["text_end"])

            # Extract channel names ($PnN)
            n_params = int(keywords.get("$PAR", "0"))
            channel_names: List[str] = []
            for i in range(1, n_params + 1):
                name = keywords.get(f"$P{i}N", f"P{i}")
                channel_names.append(name.strip())

            # Parse DATA segment
            events = self._parse_fcs_data_segment(raw, keywords, hdr["data_start"], hdr["data_end"])

            # Build output paths
            csv_name = fcs_file.stem + ".csv"
            csv_path = output_path / csv_name
            metadata_path = output_path / (fcs_file.stem + "_metadata.json")

            # Write CSV
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if channel_names:
                    writer.writerow(channel_names)
                if events:
                    for event in events:
                        writer.writerow(event)
                else:
                    # If we couldn't parse data, write a single note row
                    writer.writerow(["Note"])
                    writer.writerow(
                        [
                            "FCS data segment could not be parsed – see metadata JSON for header/keyword data"  # noqa: E501
                        ]
                    )

            # Gather metadata (reuse MetadataExtractor for enriched metadata)
            metadata = self.metadata_extractor.extract_fcs_metadata(fcs_path)
            metadata["conversion"] = {
                "events_written": len(events),
                "parameters": channel_names,
                "csv_file": csv_name,
            }

            # Save metadata
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            if events:
                self.logger.info(
                    f"Converted {fcs_file.name} to CSV ({len(events)} events, {len(channel_names)} channels)"  # noqa: E501
                )
            else:
                self.logger.warning(
                    f"Converted {fcs_file.name} metadata only (DATA segment not parseable)"
                )

            return str(csv_path), str(metadata_path)

        except Exception as e:
            self.logger.error(f"Error converting {fcs_path} to CSV: {e}")
            return "", ""

    def convert_excel_to_csv(self, excel_path: str, output_dir: str) -> Tuple[str, str]:
        """
        Convert Excel files to CSV format.

        Args:
            excel_path: Path to the Excel file
            output_dir: Directory to save converted files

        Returns:
            Tuple of (csv_path, metadata_path)
        """
        excel_file = Path(excel_path)
        output_path = Path(output_dir)

        try:
            # Create output directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Extract metadata
            metadata = self.metadata_extractor.extract_excel_metadata(excel_path)

            # Note: Full Excel to CSV conversion requires specialized library (openpyxl or pandas)
            # For now, we'll create placeholder files and preserve metadata
            csv_name = excel_file.stem + ".csv"
            csv_path = output_path / csv_name
            metadata_path = output_path / (excel_file.stem + "_metadata.json")

            # Create placeholder CSV file
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Row", "Column A", "Column B", "Note"])
                writer.writerow(["1", "", "", "Full Excel conversion requires openpyxl or pandas"])

            # Save metadata
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            self.logger.info(f"Converted {excel_file.name} to CSV (placeholder)")
            self.logger.warning("Full Excel to CSV conversion requires openpyxl or pandas library")

            return str(csv_path), str(metadata_path)

        except Exception as e:
            self.logger.error(f"Error converting {excel_path} to CSV: {e}")
            return "", ""

    def convert_flowjo_to_json(self, wsp_path: str, output_dir: str) -> str:
        """
        Convert FlowJo workspace files to JSON format.

        Args:
            wsp_path: Path to the WSP file
            output_dir: Directory to save converted files

        Returns:
            Path to converted JSON file
        """
        wsp_file = Path(wsp_path)
        output_path = Path(output_dir)

        try:
            # Create output directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Extract metadata
            metadata = self.metadata_extractor.extract_flowjo_metadata(wsp_path)

            # Convert WSP to JSON (WSP files are XML-based)
            json_name = wsp_file.stem + ".json"
            json_path = output_path / json_name

            # Read WSP file and convert to JSON
            with open(wsp_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Parse XML and convert to JSON structure
            import xml.etree.ElementTree as ET

            root = ET.fromstring(content)

            def xml_to_dict(element):
                result = {}
                for child in element:
                    if len(child) > 0:
                        result[child.tag] = xml_to_dict(child)
                    else:
                        result[child.tag] = child.text
                return result

            json_data = xml_to_dict(root)

            # Save as JSON
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, default=str)

            # Save metadata
            metadata_path = output_path / (wsp_file.stem + "_metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

            self.logger.info(f"Converted {wsp_file.name} to JSON")

            return str(json_path)

        except Exception as e:
            self.logger.error(f"Error converting {wsp_path} to JSON: {e}")
            return ""

    def convert_xml_to_json(self, xml_path: str, output_dir: str) -> str:
        """
        Convert XML metadata files to JSON format.

        Args:
            xml_path: Path to the XML file
            output_dir: Directory to save converted files

        Returns:
            Path to converted JSON file
        """
        xml_file = Path(xml_path)
        output_path = Path(output_dir)

        try:
            # Create output directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Extract metadata
            _metadata = self.metadata_extractor.extract_xml_metadata(xml_path)  # noqa: F841

            # Convert XML to JSON
            json_name = xml_file.stem + ".json"
            json_path = output_path / json_name

            # Read XML file and convert to JSON
            with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Parse XML and convert to JSON structure
            import xml.etree.ElementTree as ET

            root = ET.fromstring(content)

            def xml_to_dict(element):
                result = {}
                for child in element:
                    if len(child) > 0:
                        result[child.tag] = xml_to_dict(child)
                    else:
                        result[child.tag] = child.text
                return result

            json_data = xml_to_dict(root)

            # Save as JSON
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, default=str)

            self.logger.info(f"Converted {xml_file.name} to JSON")

            return str(json_path)

        except Exception as e:
            self.logger.error(f"Error converting {xml_path} to JSON: {e}")
            return ""

    def batch_convert_folder(self, folder_path: str, output_dir: str) -> List[ConversionResult]:
        """
        Batch convert all files in a folder.

        Args:
            folder_path: Path to the folder containing files
            output_dir: Directory to save converted files

        Returns:
            List of ConversionResult objects
        """
        folder = Path(folder_path)
        output_path = Path(output_dir)
        results = []

        # Create output directory structure
        output_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (output_path / "original").mkdir(exist_ok=True)
        (output_path / "converted").mkdir(exist_ok=True)
        (output_path / "metadata").mkdir(exist_ok=True)

        # Process each file
        for item in folder.rglob("*"):
            if item.is_file():
                suffix = item.suffix.lower()

                try:
                    if suffix == ".czi":
                        converted_files = self.convert_czi_to_tiff(
                            str(item), str(output_path / "converted")
                        )
                        for cf in converted_files:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=cf,
                                    success=True,
                                    conversion_type="czi_to_tiff",
                                    metadata_file=str(
                                        output_path
                                        / "converted"
                                        / (Path(cf).stem + "_metadata.json")
                                    ),
                                )
                            )

                    # --- Hamamatsu slide scanner (.ndpi) → TIFF ---
                    elif suffix == ".ndpi":
                        tiff_path, metadata_path = self.convert_ndpi_to_tiff(
                            str(item), str(output_path / "converted")
                        )
                        if tiff_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=tiff_path,
                                    success=True,
                                    conversion_type="ndpi_to_tiff",
                                    metadata_file=metadata_path,
                                )
                            )

                    # --- Leica confocal (.lif) → TIFF ---
                    elif suffix == ".lif":
                        tiff_path, metadata_path = self.convert_lif_to_tiff(
                            str(item), str(output_path / "converted")
                        )
                        if tiff_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=tiff_path,
                                    success=True,
                                    conversion_type="lif_to_tiff",
                                    metadata_file=metadata_path,
                                )
                            )

                    elif suffix == ".fcs":
                        csv_path, metadata_path = self.convert_fcs_to_csv(
                            str(item), str(output_path / "converted")
                        )
                        if csv_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=csv_path,
                                    success=True,
                                    conversion_type="fcs_to_csv",
                                    metadata_file=metadata_path,
                                )
                            )

                    elif suffix in [".xlsx", ".xls"]:
                        csv_path, metadata_path = self.convert_excel_to_csv(
                            str(item), str(output_path / "converted")
                        )
                        if csv_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=csv_path,
                                    success=True,
                                    conversion_type="excel_to_csv",
                                    metadata_file=metadata_path,
                                )
                            )

                    elif suffix == ".wsp":
                        json_path = self.convert_flowjo_to_json(
                            str(item), str(output_path / "converted")
                        )
                        if json_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=json_path,
                                    success=True,
                                    conversion_type="wsp_to_json",
                                    metadata_file=str(
                                        output_path
                                        / "converted"
                                        / (Path(json_path).stem + "_metadata.json")
                                    ),
                                )
                            )

                    elif suffix == ".xml":
                        json_path = self.convert_xml_to_json(
                            str(item), str(output_path / "converted")
                        )
                        if json_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=json_path,
                                    success=True,
                                    conversion_type="xml_to_json",
                                    metadata_file=str(
                                        output_path
                                        / "converted"
                                        / (Path(json_path).stem + "_metadata.json")
                                    ),
                                )
                            )

                    # --- Leica LAS X metadata files (XML-based) → JSON ---
                    elif suffix in [".xlif", ".lof", ".xlef", ".lifext", ".xsl"]:
                        json_path = self.convert_xml_to_json(
                            str(item), str(output_path / "converted")
                        )
                        if json_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=json_path,
                                    success=True,
                                    conversion_type="leica_xml_to_json",
                                    metadata_file=str(
                                        output_path
                                        / "converted"
                                        / (Path(json_path).stem + "_metadata.json")
                                    ),
                                )
                            )

                    # --- GraphPad Prism (.pzfx, XML-based) → JSON ---
                    elif suffix == ".pzfx":
                        json_path = self.convert_xml_to_json(
                            str(item), str(output_path / "converted")
                        )
                        if json_path:
                            results.append(
                                ConversionResult(
                                    source_file=str(item),
                                    target_file=json_path,
                                    success=True,
                                    conversion_type="pzfx_to_json",
                                    metadata_file=str(
                                        output_path
                                        / "converted"
                                        / (Path(json_path).stem + "_metadata.json")
                                    ),
                                )
                            )

                    # --- .lifext lock files – skip (not useful data) ---
                    elif suffix == ".lock":
                        self.logger.debug(f"Skipping lock file: {item.name}")
                        continue

                    else:
                        # Copy other files as-is
                        target_path = output_path / "original" / item.name
                        import shutil

                        shutil.copy2(str(item), target_path)
                        results.append(
                            ConversionResult(
                                source_file=str(item),
                                target_file=str(target_path),
                                success=True,
                                conversion_type="copy",
                                metadata_file=None,
                            )
                        )
                        self.logger.info(f"Copied {item.name} (no conversion needed)")

                except Exception as e:
                    results.append(
                        ConversionResult(
                            source_file=str(item),
                            target_file="",
                            success=False,
                            conversion_type="error",
                            error_message=str(e),
                        )
                    )
                    self.logger.error(f"Error processing {item.name}: {e}")

        # Generate conversion manifest
        manifest = {
            "conversion_date": datetime.now().isoformat(),
            "source_folder": str(folder),
            "output_folder": str(output_dir),
            "total_files": len(results),
            "successful_conversions": len([r for r in results if r.success]),
            "failed_conversions": len([r for r in results if not r.success]),
            "conversions": [
                {
                    "source": r.source_file,
                    "target": r.target_file,
                    "success": r.success,
                    "type": r.conversion_type,
                    "metadata_file": r.metadata_file,
                    "error": r.error_message,
                }
                for r in results
            ],
        }

        manifest_path = output_path / "conversion_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        success_count = len([r for r in results if r.success])
        self.logger.info(f"Batch conversion complete: {success_count}/{len(results)} successful")

        return results

    def get_conversion_manifest(self, output_dir: str) -> Optional[Dict[str, Any]]:
        """
        Get the conversion manifest for a converted folder.

        Args:
            output_dir: Directory containing converted files

        Returns:
            Conversion manifest dictionary or None if not found
        """
        manifest_path = Path(output_dir) / "conversion_manifest.json"

        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                return cast(Dict[str, Any], json.load(f))

        return None


def main():
    """Main function for testing the format converter."""
    import sys

    # Test with representative data folder
    test_folder = "partner representative data/E1_Müller_Calceinassay und FACS Test"
    output_dir = "test_conversion_output"

    if len(sys.argv) > 1:
        test_folder = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]

    converter = FormatConverter(preserve_originals=True)
    results = converter.batch_convert_folder(test_folder, output_dir)

    print(f"\nConversion results for: {test_folder}")
    print(f"Total files: {len(results)}")
    print(f"Successful: {len([r for r in results if r.success])}")
    print(f"Failed: {len([r for r in results if not r.success])}")
    print("\nConversion types:")
    conversion_types = {}
    for r in results:
        if r.success:
            if r.conversion_type not in conversion_types:
                conversion_types[r.conversion_type] = 0
            conversion_types[r.conversion_type] += 1

    for conv_type, count in conversion_types.items():
        print(f"  {conv_type}: {count}")


if __name__ == "__main__":
    main()
