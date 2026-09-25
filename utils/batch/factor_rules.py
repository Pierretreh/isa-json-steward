"""
Declarative factor-extraction engine for partner data experiments.

This module implements the rule schema defined in
``config/factor_extraction_rules.json`` (overridable by a profile's
``config/factor_extraction_rules.json``).  The engine is pure and
deterministic: it performs no I/O, takes the parsed rules as input, and
can be unit-tested in isolation.

Two rule schemas are supported:

* **Full schema** (preferred)::

    {
        "rules": [
            {
                "name": "explant_facs_treatment_donor",
                "match_experiment_name": {"contains_all": [...], "contains_any": [...]},
                "min_factors_to_match": 2,
                "scan_subfolders": false,
                "factors": [
                    {"name": "donor", "regex": "_([AB])_", "group": 1},
                    ...
                ]
            }
        ],
        "factor_aliases": {"treatment": {"control": ["controlle", ...]}, ...}
    }

* **Legacy schema** (used by the minimal core default)::

    {
        "rules": [
            {"pattern": "E(?P<experiment_number>\\d+)",
             "extract": {"experiment_number": "int"}}
        ]
    }

Regexes are applied with :func:`re.search` against the raw name *and* the
``pathlib.Path(name).stem`` (which strips the extension) so that
``$``-anchored patterns work on both file names and plain strings.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

__all__ = ["FactorRulesExtractor"]

#: Token delimiter pattern for file-to-sample matching.  Digits, letters,
#: and commas are kept inside tokens so values like "0,1um" survive.
_TOKEN_RE = re.compile(r"[^0-9A-Za-z,]+")


def _name_variants(name: str) -> List[str]:
    """Return the extension-less stem first, then the raw name.

    The stem is preferred so that ``$``-anchored patterns (e.g. the E100
    treatment rule) are not contaminated by the file extension; the raw
    name is kept as a fallback for patterns that depend on it.
    """
    name = name or ""
    stem = Path(name).stem
    return [name] if stem == name else [stem, name]


def _tokenize(text: str) -> List[str]:
    """Split *text* into lowercase alphanumeric/comma tokens."""
    return [t.lower() for t in _TOKEN_RE.split(text or "") if t]


class FactorRulesExtractor:
    """Evaluate factor-extraction rules from ``factor_extraction_rules.json``.

    The extractor is stateless apart from the rules and aliases it was
    constructed with; all methods are pure and deterministic.

    Args:
        rules: Parsed ``factor_extraction_rules.json`` content (dict with
            a ``rules`` list; may also contain ``factor_aliases``).
        aliases: Optional explicit factor-alias mapping
            (``{factor: {canonical: [aliases]}}``).  When omitted, the
            ``factor_aliases`` section of *rules* is used.
    """

    def __init__(
        self,
        rules: Optional[Dict[str, Any]] = None,
        aliases: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> None:
        self._rules_data = rules or {}
        self._aliases: Dict[str, Dict[str, List[str]]] = (
            dict(aliases)
            if aliases is not None
            else dict(self._rules_data.get("factor_aliases") or {})
        )

    # ── Accessors ────────────────────────────────────────────────────────

    @property
    def rules(self) -> List[Dict[str, Any]]:
        """The list of rule definitions."""
        return list(self._rules_data.get("rules") or [])

    @property
    def aliases(self) -> Dict[str, Dict[str, List[str]]]:
        """Factor aliases: ``{factor_name: {canonical: [alias, ...]}}``."""
        return self._aliases

    # ── Rule gating ──────────────────────────────────────────────────────

    def _rule_matches_experiment(self, rule: Dict[str, Any], exp_name: str) -> bool:
        """Check the rule's ``match_experiment_name`` gate against *exp_name*."""
        gate = rule.get("match_experiment_name")
        if not gate:
            return True
        name = (exp_name or "").lower()
        contains_all = gate.get("contains_all") or []
        contains_any = gate.get("contains_any") or []
        if contains_all and not all(t in name for t in contains_all):
            return False
        if contains_any and not any(t in name for t in contains_any):
            return False
        return True

    # ── Factor evaluation ────────────────────────────────────────────────

    def _extract_factor_values(
        self,
        rule: Dict[str, Any],
        exp_name: str,
        file_names: List[str],
        subfolder_names: Optional[List[str]],
    ) -> Tuple[Dict[str, Set[str]], Dict[str, List[Tuple[str, str]]], Set[str]]:
        """Run one full-schema rule against the given names.

        Returns:
            ``(factor_values, per_name_matches, matched_names)`` where
            ``factor_values`` maps factor name -> set of values (including
            ``default_if_absent`` values), ``per_name_matches`` maps each
            scanned name -> ordered list of (factor, value) pairs, and
            ``matched_names`` is the set of factor names that were
            *explicitly* matched (defaults excluded) – used for the
            ``min_factors_to_match`` gate.
        """
        scan_subfolders = bool(rule.get("scan_subfolders"))
        names: List[str] = []
        if scan_subfolders:
            names.append(exp_name or "")
        for fn in file_names or []:
            if fn:
                names.append(fn)
        if scan_subfolders:
            for sf in subfolder_names or []:
                if sf:
                    names.append(sf)

        factor_defs: List[Dict[str, Any]] = rule.get("factors") or []
        factor_values: Dict[str, Set[str]] = {}
        per_name: Dict[str, List[Tuple[str, str]]] = {}
        matched_names: Set[str] = set()

        for fdef in factor_defs:
            fname = fdef.get("name")
            pattern = fdef.get("regex")
            if not fname or not pattern:
                continue
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue

            default = fdef.get("default_if_absent")
            for name in names:
                variants = _name_variants(name)
                match = None
                for v in variants:
                    match = compiled.search(v)
                    if match:
                        break
                if match is None:
                    continue
                group = fdef.get("group")
                value: str
                if group is not None:
                    try:
                        value = match.group(group)
                    except (IndexError, re.error):
                        value = match.group(0)
                else:
                    value = match.group(0)
                value = value.strip()
                if not value:
                    continue
                value_map: Dict[str, str] = fdef.get("value_map") or {}
                mapped = value_map.get(value, value_map.get(value.lower()))
                value = mapped if mapped else value
                suffix = fdef.get("suffix")
                if suffix:
                    value = f"{value}{suffix}"

                factor_values.setdefault(fname, set()).add(value)
                matched_names.add(fname)
                per_name.setdefault(name, []).append((fname, value))

            if default and fname not in factor_values:
                factor_values[fname] = {str(default)}

        return factor_values, per_name, matched_names

    # ── Main API ─────────────────────────────────────────────────────────

    def extract(
        self, exp_name: str, file_names: List[str], subfolder_names: Optional[List[str]] = None
    ) -> Optional[Tuple[Dict[str, Set[str]], List[Dict[str, str]]]]:
        """Extract factors from file/subfolder names for *exp_name*.

        Args:
            exp_name: Experiment (folder) name used for rule gating and,
                when ``scan_subfolders`` is set, as a scanned name.
            file_names: File names (with or without extensions) to scan.
            subfolder_names: Subdirectory names to scan (only honoured by
                rules with ``scan_subfolders: true``).

        Returns:
            ``(factor_values, combinations)`` where ``factor_values`` maps
            factor name -> set of values and ``combinations`` is an ordered,
            de-duplicated list of per-name factor dicts; or ``None`` when no
            rule fires.
        """
        rules = [r for r in self.rules if isinstance(r, dict)]
        for rule in rules:
            if not self._rule_matches_experiment(rule, exp_name):
                continue

            if rule.get("factors"):
                factor_values, per_name, matched = self._extract_factor_values(
                    rule, exp_name, file_names, subfolder_names
                )
            elif rule.get("pattern"):
                factor_values, per_name, matched = self._extract_legacy_rule(
                    rule, exp_name, file_names, subfolder_names
                )
            else:
                continue

            # Gate on explicitly matched factors only – default_if_absent
            # values must not count toward the minimum.
            min_factors = int(rule.get("min_factors_to_match") or 1)
            if len(matched) < min_factors:
                continue

            combos: List[Dict[str, str]] = []
            seen = set()
            for name, pairs in per_name.items():
                combo: Dict[str, str] = dict(pairs)
                key = tuple(sorted(combo.items()))
                if key in seen:
                    continue
                seen.add(key)
                combos.append(combo)

            return factor_values, combos

        return None

    # ── Legacy schema ────────────────────────────────────────────────────

    def _extract_legacy_rule(
        self,
        rule: Dict[str, Any],
        exp_name: str,
        file_names: List[str],
        subfolder_names: Optional[List[str]],
    ) -> Tuple[Dict[str, Set[str]], Dict[str, List[Tuple[str, str]]], Set[str]]:
        """Evaluate a legacy ``pattern``/``extract`` rule.

        The pattern is applied (``re.search``) against the experiment name
        and each scanned name; named groups are converted per the
        ``extract`` spec (``"int"`` / ``"str"``).
        """
        pattern = rule.get("pattern")
        if not pattern:
            return {}, {}, set()
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return {}, {}, set()
        extract_spec: Dict[str, str] = rule.get("extract") or {}

        names = _name_variants(exp_name)
        for fn in file_names or []:
            if fn:
                names.extend(_name_variants(fn))
        if rule.get("scan_subfolders"):
            for sf in subfolder_names or []:
                if sf:
                    names.extend(_name_variants(sf))

        factor_values: Dict[str, Set[str]] = {}
        per_name: Dict[str, List[Tuple[str, str]]] = {}
        for name in names:
            if not name:
                continue
            match = compiled.search(name)
            if not match:
                continue
            groups: Dict[str, str] = {}
            for gname, _g in match.groupdict().items():
                if _g is None:
                    continue
                spec = extract_spec.get(gname, "str")
                raw = _g.strip()
                if spec == "int":
                    try:
                        groups[gname] = str(int(raw))
                    except (TypeError, ValueError):
                        groups[gname] = raw
                else:
                    groups[gname] = raw
            if not groups:
                continue
            for gname, value in groups.items():
                factor_values.setdefault(gname, set()).add(value)
            per_name.setdefault(name, []).extend(groups.items())

        return factor_values, per_name, set(factor_values.keys())

    # ── File-to-sample mapping ───────────────────────────────────────────

    def map_file_to_sample(
        self,
        filename: str,
        samples: List[Dict[str, Any]],
        aliases: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> Optional[str]:
        """Map a file name to the best-matching sample ``@id``.

        Matching is delimited-token based with exact matches scoring higher
        than partial (substring) matches, so e.g. a single-letter donor
        token never matches inside a longer word, and factor ``Control``
        beats the partial ``Control erneut`` for a plain "Control" file.

        Args:
            filename: File name (extension included or not).
            samples: Sample dicts as produced for study export, each with
                ``@id`` and ``factorValues`` entries of the form
                ``{"category": {"@id": "#factor/<name>"},
                "value": {"annotationValue": ...}}``.
            aliases: Optional factor-alias mapping; defaults to the
                extractor's aliases.

        Returns:
            The ``@id`` of the best-matching sample, or ``None`` when no
            sample scored above zero.  Ties resolve to the first sample.
        """
        if not samples:
            return None
        if len(samples) == 1:
            return samples[0].get("@id")

        alias_map = self._aliases if aliases is None else (aliases or {})
        tokens = _tokenize(Path(filename).stem)
        if not tokens:
            return None

        best_id: Optional[str] = None
        best_score = 0
        for sample in samples:
            score = self._score_sample(tokens, sample, alias_map)
            if score > best_score:
                best_score = score
                best_id = sample.get("@id")

        return best_id if best_score > 0 else None

    @staticmethod
    def _expand_values(
        value: str, factor_name: str, alias_map: Dict[str, Dict[str, List[str]]]
    ) -> List[str]:
        """Return *value* plus its aliases (lower-cased, de-duplicated)."""
        out = [value.lower()]
        canon_map = (alias_map or {}).get(factor_name, {})
        for canonical, alias_list in canon_map.items():
            if value.lower() == canonical.lower():
                out.extend(a.lower() for a in alias_list)
        seen: List[str] = []
        for v in out:
            if v and v not in seen:
                seen.append(v)
        return seen

    def _score_sample(
        self, tokens: List[str], sample: Dict[str, Any], alias_map: Dict[str, Dict[str, List[str]]]
    ) -> int:
        """Score a sample against the file's tokens (higher = better)."""
        score = 0
        for fv in sample.get("factorValues") or []:
            cat = (fv.get("category") or {}).get("@id", "")
            factor_name = cat.rsplit("/", 1)[-1] if cat else ""
            raw_value = (fv.get("value") or {}).get("annotationValue", "")
            if not raw_value:
                continue
            for value in self._expand_values(str(raw_value), factor_name, alias_map):
                v = value.strip().lower()
                if not v:
                    continue
                words = [w for w in v.split() if w] or [v]
                for i, word in enumerate(tokens):
                    if word == v:
                        # Exact token match (single-word value or full token)
                        score += len(v)
                        break
                    if (
                        len(words) > 1
                        and i + len(words) <= len(tokens)
                        and all(tokens[i + j] == words[j] for j in range(len(words)))
                    ):
                        # Contiguous multi-word run, e.g. "control erneut"
                        score += len(v)
                        break
                    if len(word) >= 3 and len(v) >= 3 and v in word:
                        # Substring: "isoprop" inside "isopropanol"
                        # (single/double-letter values never match inside words)
                        score += max(1, len(v) // 2)
                        break
                    if len(word) >= 3 and len(v) >= 4 and word in v:
                        # Reverse containment: word is a piece of the value
                        score += max(1, len(word) // 8)
                        break
        return score
