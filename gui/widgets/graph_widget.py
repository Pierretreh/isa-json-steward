"""
Interactive Graph Widget for Ontology Visualization.

This module provides a custom widget for rendering interactive graphs
using PyQt6's QGraphicsScene and QGraphicsView, with category-clustered
hierarchical layout, hover highlighting, collapsible branches, and
curved cross-category edges.
"""

import math
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# ── Color scheme for different categories ──────────────────────────────

CATEGORY_COLORS = {
    "Materials": QColor("#3498db"),
    "Processes": QColor("#2ecc71"),
    "Protocols": QColor("#2ecc71"),
    "Assays": QColor("#9b59b6"),
    "Parameters": QColor("#e67e22"),
    "DataFiles": QColor("#1abc9c"),
    "External": QColor("#95a5a6"),
    "Devices": QColor("#e74c3c"),
    "default": QColor("#95a5a6"),
}

# Edge colors by relation type
EDGE_COLORS = {
    "subClassOf": QColor("#7f8c8d"),
    "exactMatch": QColor("#1abc9c"),
    "closeMatch": QColor("#1abc9c"),
    "hasInput": QColor("#3498db"),
    "hasOutput": QColor("#e74c3c"),
    "hasParameter": QColor("#e67e22"),
    "hasExpectedFormat": QColor("#9b59b6"),
    "default": QColor("#95a5a6"),
}

# Layout constants
CATEGORY_REGION_RADIUS_BASE = 300
LAYER_SPACING_Y = 130
NODE_SPACING_X = 200
COLLAPSE_TOGGLE_RADIUS = 8
MIN_NODE_RADIUS = 22
MAX_NODE_RADIUS = 35
NODE_DEFAULT_RADIUS = 28
FORCE_ITERATIONS = 40
FORCE_REPULSION = 50000
FORCE_ATTRACTION = 0.02
FORCE_CENTER_GRAVITY = 0.06
FORCE_DAMPING = 0.8
FORCE_OPTIMAL_EDGE = 100


# ── Graph Node ─────────────────────────────────────────────────────────


class GraphNode(QGraphicsItem):
    """A node in the graph representing an ontology term."""

    def __init__(self, uri: str, label: str, node_type: str, category: str = "", graph_widget=None):
        super().__init__()
        self.uri = uri
        self.label = label
        self.node_type = node_type
        self.category = category
        self._graph_widget = graph_widget

        # Node appearance — radius will be set later by degree
        self.radius: float = NODE_DEFAULT_RADIUS
        self.color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["default"])
        self.selected_color = QColor("#f1c40f")
        self.highlight_color = QColor("#f39c12")

        # Interaction state
        self._highlighted = False
        self._dimmed = False
        self._is_hovered = False

        # Collapsible state
        self._collapsed = False
        self._child_uris: Set[str] = set()
        self._toggle_item: Optional[QGraphicsEllipseItem] = None
        self._toggle_label: Optional[QGraphicsTextItem] = None
        self._hidden_count = 0
        self._hidden_badge: Optional[QGraphicsTextItem] = None

        # Set flags for interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Tooltip
        self.setToolTip(f"{self.label}\nType: {self.node_type}\nURI: {self.uri}")

        # Cache position
        self._position = QPointF(0, 0)

        # Label item (below node)
        self.label_item = QGraphicsTextItem(self.label, self)
        font = QFont()
        font.setPointSize(9)
        self.label_item.setFont(font)
        self._center_label()

    def _center_label(self):
        """Center the label below the node circle."""
        label_rect = self.label_item.boundingRect()
        self.label_item.setPos(-label_rect.width() / 2, self.radius + 5)

    def set_radius(self, r: float):
        """Set node radius and re-center label."""
        self.radius = r
        self._center_label()

    # ── Painting ───────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        label_rect = self.label_item.boundingRect()
        toggle_extra = 20 if self._child_uris else 0
        badge_extra = 20 if self._hidden_count > 0 else 0
        return QRectF(
            -self.radius - 8,
            -self.radius - 8,
            (self.radius * 2) + 16,
            (self.radius * 2) + 16 + label_rect.height() + 14 + toggle_extra + badge_extra,
        )

    def paint(self, painter: Optional[QPainter], option, widget=None):
        """Paint the node."""
        if painter is None:
            return
        r = self.radius  # shorthand

        # Selection glow
        if self.isSelected():
            glow_pen = QPen(self.selected_color, 4)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-r - 3, -r - 3, r * 2 + 6, r * 2 + 6))

        # Hover / highlight glow
        if self._is_hovered or self._highlighted:
            glow_color = QColor(self.highlight_color)
            glow_color.setAlpha(80)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(QRectF(-r - 6, -r - 6, r * 2 + 12, r * 2 + 12))

        # Node circle with gradient
        gradient = QRadialGradient(0, 0, r)
        if self._dimmed:
            c = QColor(self.color)
            c.setAlpha(60)
            gradient.setColorAt(0, c.lighter(130))
            gradient.setColorAt(1, c)
        else:
            gradient.setColorAt(0, self.color.lighter(130))
            gradient.setColorAt(1, self.color)

        pen_color = QColor(Qt.GlobalColor.black)
        if self._dimmed:
            pen_color.setAlpha(60)
        painter.setPen(QPen(pen_color, 2))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

        # Short label on node
        if len(self.label) <= 8 and not self._dimmed:
            painter.setPen(Qt.GlobalColor.white)
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(-r, -r, r * 2, r * 2), Qt.AlignmentFlag.AlignCenter, self.label)

        # Collapse toggle button
        if self._child_uris:
            tr = float(COLLAPSE_TOGGLE_RADIUS)
            ty = r + 3.0
            painter.setPen(QPen(QColor("#555"), 1))
            painter.setBrush(QBrush(QColor("#ecf0f1")))
            painter.drawEllipse(QRectF(-tr, ty, tr * 2, tr * 2))
            painter.setPen(QColor("#2c3e50"))
            toggle_font = QFont()
            toggle_font.setPointSize(8)
            toggle_font.setBold(True)
            painter.setFont(toggle_font)
            symbol = "+" if self._collapsed else "−"
            painter.drawText(QRectF(-tr, ty, tr * 2, tr * 2), Qt.AlignmentFlag.AlignCenter, symbol)

        # Hidden count badge (when collapsed)
        if self._collapsed and self._hidden_count > 0:
            bx = r + 2.0
            by = -r - 2.0
            painter.setPen(QPen(QColor("#e74c3c"), 1))
            painter.setBrush(QBrush(QColor("#e74c3c")))
            painter.drawEllipse(QRectF(bx - 8, by - 8, 16, 16))
            painter.setPen(Qt.GlobalColor.white)
            badge_font = QFont()
            badge_font.setPointSize(7)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.drawText(
                QRectF(bx - 8, by - 8, 16, 16),
                Qt.AlignmentFlag.AlignCenter,
                str(self._hidden_count),
            )

    # ── Hover events ───────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        if self._graph_widget:
            self._graph_widget._apply_hover_effects(self.uri)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        if self._graph_widget:
            self._graph_widget._clear_hover_effects()
        super().hoverLeaveEvent(event)

    # ── Mouse click (collapse toggle) ──────────────────────────────────

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._child_uris
            and self._is_toggle_click(event.pos())
        ):
            self._toggle_collapse()
            return
        super().mousePressEvent(event)

    def _is_toggle_click(self, pos: QPointF) -> bool:
        """Check if click is on the collapse toggle button area."""
        ty = self.radius + 3
        toggle_center = QPointF(0, ty)
        return (pos - toggle_center).manhattanLength() < COLLAPSE_TOGGLE_RADIUS * 2

    def _toggle_collapse(self):
        """Toggle collapsed state and trigger relayout."""
        self._collapsed = not self._collapsed
        if self._graph_widget:
            self._graph_widget._on_node_collapse_toggled(self.uri, self._collapsed)
        self.update()

    # ── Context menu ───────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu()
        if self._child_uris:
            action_text = "Expand" if self._collapsed else "Collapse"
            toggle_action = QAction(action_text, menu)
            toggle_action.triggered.connect(self._toggle_collapse)
            menu.addAction(toggle_action)

        focus_action = QAction("Focus on neighbors", menu)
        focus_action.triggered.connect(self._focus_neighbors)
        menu.addAction(focus_action)

        menu.exec(event.screenPos())

    def _focus_neighbors(self):
        if self._graph_widget:
            self._graph_widget._focus_on_node(self.uri)

    # ── State control ──────────────────────────────────────────────────

    def set_highlighted(self, active: bool):
        self._highlighted = active
        self.update()

    def set_dimmed(self, dim: bool):
        self._dimmed = dim
        # Also dim the label
        if dim:
            self.label_item.setOpacity(0.3)
        else:
            self.label_item.setOpacity(1.0)
        self.update()

    # ── Geometry change tracking ───────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            self._position = value
        return super().itemChange(change, value)

    def get_position(self) -> QPointF:
        return self._position


# ── Graph Edge ─────────────────────────────────────────────────────────


class GraphEdge(QGraphicsItem):
    """An edge in the graph representing a relationship between nodes."""

    def __init__(
        self,
        source: GraphNode,
        target: GraphNode,
        relation_type: str,
        is_cross_category: bool = False,
    ):
        super().__init__()
        self.source = source
        self.target = target
        self.relation_type = relation_type
        self.is_cross_category = is_cross_category

        # Edge appearance
        self.color = EDGE_COLORS.get(relation_type, EDGE_COLORS["default"])
        self.width = 2
        self.arrow_size = 10

        # Interaction state
        self._highlighted = False
        self._dimmed = False
        self._is_hovered = False

        # Label (hidden by default)
        self._label_item: Optional[QGraphicsTextItem] = None

        self.setZValue(-1)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        sp = self.source.pos()
        tp = self.target.pos()
        padding = self.arrow_size + 20
        return QRectF(
            min(sp.x(), tp.x()) - padding,
            min(sp.y(), tp.y()) - padding,
            abs(sp.x() - tp.x()) + padding * 2,
            abs(sp.y() - tp.y()) + padding * 2,
        )

    def _get_bezier_path(self) -> QPainterPath:
        """Return a cubic bezier path for cross-category edges."""
        sp = self.source.pos()
        tp = self.target.pos()
        mid = QPointF((sp.x() + tp.x()) / 2, (sp.y() + tp.y()) / 2)

        # Perpendicular offset for control point
        dx = tp.x() - sp.x()
        dy = tp.y() - sp.y()
        length = math.sqrt(dx * dx + dy * dy) or 1
        nx, ny = -dy / length, dx / length

        # Offset magnitude — larger for longer edges
        offset = length * 0.25
        cp = QPointF(mid.x() + nx * offset, mid.y() + ny * offset)

        path = QPainterPath(sp)
        path.cubicTo(cp, cp, tp)
        return path

    def _get_straight_line_points(self) -> Tuple[QPointF, QPointF]:
        """Return adjusted start/end points for a straight line."""
        sp = self.source.pos()
        tp = self.target.pos()
        line = QLineF(sp, tp)
        if line.length() == 0:
            return sp, tp
        sr = self.source.radius
        tr = self.target.radius
        start = line.pointAt(sr / line.length())
        end = line.pointAt(1 - tr / line.length())
        return start, end

    def paint(self, painter: Optional[QPainter], option, widget=None):
        if painter is None:
            return
        # Choose pen
        pen_color = QColor(self.color)
        if self._dimmed:
            pen_color.setAlpha(40)
        pen = QPen(pen_color, self.width)
        if self.relation_type == "exactMatch":
            pen.setStyle(Qt.PenStyle.DashLine)
        if self._highlighted or self._is_hovered:
            pen.setWidth(3)
        painter.setPen(pen)

        if self.is_cross_category:
            # Draw bezier curve
            path = self._get_bezier_path()
            painter.drawPath(path)

            # Arrow at target for subClassOf
            if self.relation_type == "subClassOf":
                self._draw_arrow_on_bezier(painter, path)
        else:
            # Straight line
            start, end = self._get_straight_line_points()
            painter.drawLine(start, end)

            # Arrow for subClassOf
            if self.relation_type == "subClassOf":
                self._draw_arrow_straight(painter, start, end)

    def _draw_arrow_straight(self, painter: QPainter, start: QPointF, end: QPointF):
        """Draw an arrowhead at the end of a straight edge."""
        line = QLineF(start, end)
        angle = line.angle()
        arrow_path = QPainterPath()
        arrow_path.moveTo(end)
        for sign in [1, -1]:
            a = angle + 30 * sign
            pt = end - QPointF(
                self.arrow_size * math.cos(math.radians(a % 360)),
                self.arrow_size * math.sin(math.radians(a % 360)),
            )
            arrow_path.lineTo(pt)
        arrow_path.closeSubpath()
        painter.setBrush(QBrush(self.color))
        painter.drawPath(arrow_path)

    def _draw_arrow_on_bezier(self, painter: QPainter, path: QPainterPath):
        """Draw an arrowhead at the end of a bezier path."""
        length = path.length()
        if length < 1:
            return
        # Approximate tangent at end
        t_end = 0.99
        p1 = path.pointAtPercent(t_end - 0.01)
        p2 = path.pointAtPercent(t_end)
        angle = QLineF(p1, p2).angle()
        arrow_path = QPainterPath()
        arrow_path.moveTo(p2)
        for sign in [1, -1]:
            a = angle + 30 * sign
            pt = p2 - QPointF(
                self.arrow_size * math.cos(math.radians(a % 360)),
                self.arrow_size * math.sin(math.radians(a % 360)),
            )
            arrow_path.lineTo(pt)
        arrow_path.closeSubpath()
        painter.setBrush(QBrush(self.color))
        painter.drawPath(arrow_path)

    # ── Hover events ───────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self._show_label()
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self._hide_label()
        self.update()
        super().hoverLeaveEvent(event)

    def _show_label(self):
        if self._label_item is not None:
            return
        sp = self.source.pos()
        tp = self.target.pos()
        mid = QPointF((sp.x() + tp.x()) / 2, (sp.y() + tp.y()) / 2)
        self._label_item = QGraphicsTextItem(self.relation_type, self)
        font = QFont()
        font.setPointSize(8)
        self._label_item.setFont(font)
        self._label_item.setDefaultTextColor(QColor("#2c3e50"))
        rect = self._label_item.boundingRect()
        self._label_item.setPos(mid.x() - rect.width() / 2, mid.y() - rect.height() - 5)
        if self.scene():
            self.scene().addItem(self._label_item)

    def _hide_label(self):
        if self._label_item is not None:
            if self.scene():
                self.scene().removeItem(self._label_item)
            self._label_item = None

    # ── State control ──────────────────────────────────────────────────

    def set_highlighted(self, active: bool):
        self._highlighted = active
        self.update()

    def set_dimmed(self, dim: bool):
        self._dimmed = dim
        self.update()


# ── Category Region ────────────────────────────────────────────────────


class CategoryRegion(QGraphicsItem):
    """A semi-transparent background rectangle for a category cluster."""

    def __init__(self, category: str, center: QPointF, radius: float):
        super().__init__()
        self.category = category
        self._center = center
        self._radius = radius
        self._color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["default"])
        self.setZValue(-10)

    def boundingRect(self) -> QRectF:
        return QRectF(
            self._center.x() - self._radius - 20,
            self._center.y() - self._radius - 40,
            self._radius * 2 + 40,
            self._radius * 2 + 60,
        )

    def paint(self, painter: Optional[QPainter], option, widget=None):
        if painter is None:
            return
        rect = QRectF(
            self._center.x() - self._radius,
            self._center.y() - self._radius - 20,
            self._radius * 2,
            self._radius * 2 + 20,
        )

        # Fill
        fill_color = QColor(self._color)
        fill_color.setAlpha(18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(rect, 15, 15)

        # Border
        border_color = QColor(self._color)
        border_color.setAlpha(70)
        pen = QPen(border_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 15, 15)

        # Label
        painter.setPen(QColor(self._color))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        label_rect = QRectF(
            self._center.x() - self._radius,
            self._center.y() - self._radius - 18,
            self._radius * 2,
            20,
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.category)


# ── Zoomable Graph View ────────────────────────────────────────────────


class ZoomableGraphView(QGraphicsView):
    """QGraphicsView subclass with mouse wheel zoom support."""

    zoom_requested = pyqtSignal(float)  # requested absolute zoom level

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)

    def wheelEvent(self, event):
        """Zoom in/out with mouse wheel, respecting limits."""
        angle = event.angleDelta().y()
        if angle == 0:
            return

        factor = 1.15 if angle > 0 else 1.0 / 1.15
        current_zoom = self.transform().m11()
        requested_zoom = current_zoom * factor

        # Emit the requested zoom level — the widget will clamp and apply
        self.zoom_requested.emit(requested_zoom)


# ── Graph Widget ───────────────────────────────────────────────────────


class GraphWidget(QWidget):
    """Interactive graph widget for ontology visualization."""

    # Signals
    node_selected = pyqtSignal(str, str, str)  # uri, label, type

    def __init__(self, parent=None):
        super().__init__(parent)

        # Scene and view
        self.scene = QGraphicsScene()
        self.view = ZoomableGraphView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        from PyQt6.QtWidgets import QSizePolicy

        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Zoom state
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 20.0
        self._updating_slider = False  # guard against circular slider updates
        self._user_has_zoomed = False  # track if user manually zoomed

        # Graph data
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.nodes_data: List[Dict] = []
        self.edges_data: List[Dict] = []

        # Layout data
        self._adjacency: Dict[str, List[str]] = {}
        self._children_map: Dict[str, List[str]] = {}
        self._parent_map: Dict[str, str] = {}
        self._category_centers: Dict[str, QPointF] = {}
        self._category_regions: Dict[str, CategoryRegion] = {}
        self._hidden_nodes: Set[str] = set()

        # View dimensions
        self.view_width = 800
        self.view_height = 600

        # Setup UI
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls_layout = QHBoxLayout()

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(30)
        zoom_in_btn.clicked.connect(self.zoom_in)

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(30)
        zoom_out_btn.clicked.connect(self.zoom_out)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_view)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.fit_to_screen)

        self._show_hidden_btn = QPushButton("Show Hidden")
        self._show_hidden_btn.clicked.connect(self._show_all_hidden)
        self._show_hidden_btn.setEnabled(False)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(self.export_to_png)

        export_svg_btn = QPushButton("Export SVG")
        export_svg_btn.clicked.connect(self.export_to_svg)

        zoom_label = QLabel("Zoom:")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 2000)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(200)
        self.zoom_slider.valueChanged.connect(self._on_slider_changed)

        controls_layout.addWidget(zoom_label)
        controls_layout.addWidget(self.zoom_slider)
        controls_layout.addWidget(zoom_in_btn)
        controls_layout.addWidget(zoom_out_btn)
        controls_layout.addWidget(reset_btn)
        controls_layout.addWidget(fit_btn)
        controls_layout.addWidget(self._show_hidden_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(export_png_btn)
        controls_layout.addWidget(export_svg_btn)

        layout.addLayout(controls_layout)
        layout.addWidget(self.view)

    def _connect_signals(self):
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.view.resizeEvent = self._on_view_resize
        self.view.zoom_requested.connect(self._on_wheel_zoom)

    # ── Public API ─────────────────────────────────────────────────────

    def set_graph_data(self, nodes_data: List[Dict], edges_data: List[Dict]):
        """Set graph data and render with the enhanced layout."""
        self.nodes_data = nodes_data
        self.edges_data = edges_data
        self._hidden_nodes.clear()

        viewport = self.view.viewport()
        if viewport is not None:
            new_size = viewport.size()
            self.view_width = new_size.width()
            self.view_height = new_size.height()

        # Clear scene
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self._category_regions.clear()
        self._user_has_zoomed = False

        if not nodes_data:
            return

        # Build layout data
        self._build_layout_maps(nodes_data, edges_data)

        # Compute node degrees for sizing
        degrees = self._compute_degrees(nodes_data, edges_data)

        # Assign radii based on degree
        max_degree = max(degrees.values()) if degrees else 1
        for nd in nodes_data:
            uri = nd["uri"]
            deg = degrees.get(uri, 0)
            ratio = deg / max_degree if max_degree > 0 else 0
            nd["_radius"] = MIN_NODE_RADIUS + ratio * (MAX_NODE_RADIUS - MIN_NODE_RADIUS)

        # Run the layout
        positions = self._layout_all(nodes_data, edges_data)

        # Create node items
        for nd in nodes_data:
            uri = nd["uri"]
            node = GraphNode(
                uri=uri,
                label=nd["label"],
                node_type=nd.get("type", "Term"),
                category=nd.get("category", ""),
                graph_widget=self,
            )
            node.set_radius(nd.get("_radius", NODE_DEFAULT_RADIUS))
            # Only assign children for internal nodes (not external references)
            # External nodes are leaf references and shouldn't have collapse toggles
            if nd.get("category") == "External":
                node._child_uris = set()
            else:
                node._child_uris = set(self._children_map.get(uri, []))
            self.scene.addItem(node)
            self.nodes[uri] = node

        # Apply positions
        for nd in nodes_data:
            uri = nd["uri"]
            if uri in self.nodes and uri in positions:
                self.nodes[uri].setPos(positions[uri])

        # Create edge items
        for ed in edges_data:
            src = ed["source"]
            tgt = ed["target"]
            if src in self.nodes and tgt in self.nodes:
                src_cat = self.nodes[src].category
                tgt_cat = self.nodes[tgt].category
                is_cross = bool(src_cat != tgt_cat and src_cat and tgt_cat)
                edge = GraphEdge(
                    source=self.nodes[src],
                    target=self.nodes[tgt],
                    relation_type=ed["relation"],
                    is_cross_category=is_cross,
                )
                self.scene.addItem(edge)
                self.edges.append(edge)

        self.fit_to_screen()

    def zoom_in(self):
        self._set_zoom(self.zoom_level * 1.2)

    def zoom_out(self):
        self._set_zoom(self.zoom_level / 1.2)

    def reset_view(self):
        self._user_has_zoomed = False
        self.zoom_level = 1.0
        self.view.resetTransform()
        self.view.centerOn(0, 0)
        self.zoom_slider.setValue(100)

    def fit_to_screen(self):
        items_rect = self.scene.itemsBoundingRect()
        if items_rect.isEmpty():
            return
        viewport = self.view.viewport()
        if viewport is not None:
            vp_size = viewport.size()
            vp_w = vp_size.width()
            vp_h = vp_size.height()
            vp_aspect = vp_w / vp_h if vp_h > 0 else 1.0
            scene_aspect = (
                items_rect.width() / items_rect.height() if items_rect.height() > 0 else 1.0
            )
            cx, cy = items_rect.center().x(), items_rect.center().y()
            if vp_aspect > scene_aspect:
                new_w = items_rect.height() * vp_aspect
                new_h = items_rect.height()
            else:
                new_w = items_rect.width()
                new_h = items_rect.width() / vp_aspect
            adjusted = QRectF(cx - new_w / 2, cy - new_h / 2, new_w, new_h)
            self.scene.setSceneRect(adjusted)
        else:
            self.scene.setSceneRect(items_rect)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_level = self.view.transform().m11()
        self._updating_slider = True
        self.zoom_slider.setValue(int(self.zoom_level * 100))
        self._updating_slider = False

    def get_selected_node(self) -> Optional[Tuple[str, str, str]]:
        for item in self.scene.selectedItems():
            if isinstance(item, GraphNode):
                return (item.uri, item.label, item.node_type)
        return None

    def select_node_by_uri(self, uri: str):
        if uri in self.nodes:
            self.scene.clearSelection()
            self.nodes[uri].setSelected(True)
            self.view.centerOn(self.nodes[uri])

    def highlight_nodes(self, uris: List[str]):
        """Highlight specific nodes (e.g. search results), dim the rest."""
        for node in self.nodes.values():
            if node.uri in self._hidden_nodes:
                continue
            if node.uri in uris:
                node.set_highlighted(True)
                node.set_dimmed(False)
            else:
                node.set_highlighted(False)
                node.set_dimmed(True)
        for edge in self.edges:
            if edge.source.uri in uris or edge.target.uri in uris:
                edge.set_highlighted(True)
                edge.set_dimmed(False)
            else:
                edge.set_highlighted(False)
                edge.set_dimmed(True)
        if uris and uris[0] in self.nodes:
            self.view.centerOn(self.nodes[uris[0]])

    def clear_highlights(self):
        """Remove all highlight/dim effects."""
        for node in self.nodes.values():
            node.set_highlighted(False)
            node.set_dimmed(False)
        for edge in self.edges:
            edge.set_highlighted(False)
            edge.set_dimmed(False)

    # ── Hover effects ──────────────────────────────────────────────────

    def _apply_hover_effects(self, hovered_uri: str):
        """Dim non-connected nodes/edges, highlight neighbors."""
        # Find connected URIs
        connected = set()
        connected.add(hovered_uri)
        connected.update(self._adjacency.get(hovered_uri, []))

        for node in self.nodes.values():
            if node.uri in self._hidden_nodes:
                continue
            node.set_dimmed(node.uri not in connected)
            node.set_highlighted(node.uri in connected and node.uri != hovered_uri)

        for edge in self.edges:
            src_in = edge.source.uri in connected
            tgt_in = edge.target.uri in connected
            if src_in and tgt_in:
                edge.set_dimmed(False)
                edge.set_highlighted(True)
            else:
                edge.set_dimmed(True)
                edge.set_highlighted(False)

    def _clear_hover_effects(self):
        """Restore all nodes and edges to normal state."""
        for node in self.nodes.values():
            node.set_dimmed(False)
            node.set_highlighted(False)
        for edge in self.edges:
            edge.set_dimmed(False)
            edge.set_highlighted(False)

    # ── Focus on node ──────────────────────────────────────────────────

    def _focus_on_node(self, uri: str):
        """Zoom to show the given node and its neighbors."""
        connected = set()
        connected.add(uri)
        connected.update(self._adjacency.get(uri, []))
        if not connected:
            return
        rect = QRectF()
        for u in connected:
            if u in self.nodes:
                p = self.nodes[u].pos()
                rect = rect.united(QRectF(p.x() - 50, p.y() - 50, 100, 100))
        self.view.fitInView(rect.adjusted(-50, -50, 50, 50), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_level = self.view.transform().m11()
        self.zoom_slider.setValue(int(self.zoom_level * 100))

    # ── Collapse / expand ──────────────────────────────────────────────

    def _on_node_collapse_toggled(self, uri: str, collapsed: bool):
        """Handle collapse/expand of a node's children."""
        self._collect_descendants(uri, collapsed)
        # Update visibility
        for u in list(self._hidden_nodes):
            if u in self.nodes:
                self.nodes[u].setVisible(False)
        for u in self.nodes:
            if u not in self._hidden_nodes:
                self.nodes[u].setVisible(True)
        for edge in self.edges:
            visible = (
                edge.source.uri not in self._hidden_nodes
                and edge.target.uri not in self._hidden_nodes
            )
            edge.setVisible(visible)

        # Update hidden counts
        self._update_hidden_counts()

        # Relayout
        self._relayout_visible()

        self._show_hidden_btn.setEnabled(len(self._hidden_nodes) > 0)

    def _collect_descendants(self, uri: str, hide: bool):
        """Collect all descendants of a node and add/remove from hidden set."""
        children = self._children_map.get(uri, [])
        queue = deque(children)
        while queue:
            child = queue.popleft()
            if hide:
                self._hidden_nodes.add(child)
            else:
                self._hidden_nodes.discard(child)
            queue.extend(self._children_map.get(child, []))

    def _update_hidden_counts(self):
        """Update the hidden count badge on collapsed nodes."""
        for uri, node in self.nodes.items():
            children = self._children_map.get(uri, [])
            node._hidden_count = sum(1 for c in children if c in self._hidden_nodes)
            node.update()

    def _show_all_hidden(self):
        """Show all hidden nodes."""
        self._hidden_nodes.clear()
        for node in self.nodes.values():
            node.setVisible(True)
            node._collapsed = False
            node._hidden_count = 0
            node.update()
        for edge in self.edges:
            edge.setVisible(True)
        self._relayout_visible()
        self._show_hidden_btn.setEnabled(False)

    def _relayout_visible(self):
        """Recalculate positions for visible nodes only."""
        visible_nodes = [nd for nd in self.nodes_data if nd["uri"] not in self._hidden_nodes]
        visible_edges = [
            ed
            for ed in self.edges_data
            if (ed["source"] not in self._hidden_nodes and ed["target"] not in self._hidden_nodes)
        ]

        positions = self._layout_all(visible_nodes, visible_edges)

        for nd in visible_nodes:
            uri = nd["uri"]
            if uri in self.nodes and uri in positions:
                self.nodes[uri].setPos(positions[uri])

    # ── Zoom / resize internals ────────────────────────────────────────

    def _set_zoom(self, level: float):
        level = max(self.min_zoom, min(self.max_zoom, level))
        if level != self.zoom_level:
            scale_factor = level / self.zoom_level
            self.zoom_level = level
            self.view.scale(scale_factor, scale_factor)
            self._user_has_zoomed = True
            self._updating_slider = True
            self.zoom_slider.setValue(int(level * 100))
            self._updating_slider = False

    def _on_slider_changed(self, value: int):
        if self._updating_slider:
            return
        self._set_zoom(value / 100.0)

    def _on_wheel_zoom(self, requested_zoom: float):
        """Handle zoom from mouse wheel — applies through clamped _set_zoom."""
        self._set_zoom(requested_zoom)

    def _on_view_resize(self, event):
        viewport = self.view.viewport()
        if viewport is not None:
            new_size = viewport.size()
            self.view_width = new_size.width()
            self.view_height = new_size.height()
        # Only auto-fit on resize if user hasn't manually zoomed
        if not self._user_has_zoomed:
            self.fit_to_screen()
        QGraphicsView.resizeEvent(self.view, event)

    def _on_selection_changed(self):
        selected = self.get_selected_node()
        if selected:
            self.node_selected.emit(*selected)

    # ── Export ──────────────────────────────────────────────────────────

    def export_to_png(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Graph as PNG", "", "PNG Images (*.png);;All Files (*)"
        )
        if filepath:
            scene_rect = self.scene.itemsBoundingRect()
            from PyQt6.QtGui import QPixmap

            sz = scene_rect.size().toSize().expandedTo(scene_rect.size().toSize() * 2)
            pixmap = QPixmap(sz)
            pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene.render(painter)
            painter.end()
            pixmap.save(filepath)

    def export_to_svg(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Graph as SVG", "", "SVG Images (*.svg);;All Files (*)"
        )
        if filepath:
            from PyQt6.QtSvg import QSvgGenerator

            generator = QSvgGenerator()
            generator.setFileName(filepath)
            scene_rect = self.scene.itemsBoundingRect()
            size = scene_rect.size().toSize()
            generator.setSize(size)
            generator.setViewBox(scene_rect)
            painter = QPainter(generator)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene.render(painter)
            painter.end()

    # ── Layout Engine ──────────────────────────────────────────────────

    def _build_layout_maps(self, nodes: List[Dict], edges: List[Dict]):
        """Build adjacency, children, and parent maps from edge data."""
        node_uris = {n["uri"] for n in nodes}
        self._adjacency = {}
        self._children_map = {}
        self._parent_map = {}

        for ed in edges:
            src = ed["source"]
            tgt = ed["target"]
            rel = ed["relation"]

            # Adjacency (bidirectional for hover/neighbor lookup)
            self._adjacency.setdefault(src, []).append(tgt)
            self._adjacency.setdefault(tgt, []).append(src)

            # subClassOf: tgt is parent of src
            if rel == "subClassOf" and src in node_uris and tgt in node_uris:
                self._children_map.setdefault(tgt, []).append(src)
                self._parent_map[src] = tgt

    def _compute_degrees(self, nodes: List[Dict], edges: List[Dict]) -> Dict[str, int]:
        """Compute degree (number of connections) per node."""
        degrees: Dict[str, int] = {}
        for nd in nodes:
            degrees[nd["uri"]] = 0
        for ed in edges:
            degrees[ed["source"]] = degrees.get(ed["source"], 0) + 1
            degrees[ed["target"]] = degrees.get(ed["target"], 0) + 1
        return degrees

    def _get_category_for_node(self, uri: str, nodes: List[Dict]) -> str:
        for nd in nodes:
            if nd["uri"] == uri:
                return str(nd.get("category", "default"))
        return "default"

    def _layout_all(self, nodes: List[Dict], edges: List[Dict]) -> Dict[str, QPointF]:
        """
        Master layout: assign category regions → hierarchical layout per
        cluster → optional force refinement → return positions.
        """
        if not nodes:
            return {}

        # Determine which categories are present
        categories_present: Dict[str, List[Dict]] = {}
        for nd in nodes:
            cat = nd.get("category", "default")
            categories_present.setdefault(cat, []).append(nd)

        multi_category = len(categories_present) > 1

        # ── Phase 1: Category region assignment ────────────────────────
        if multi_category:
            self._category_centers = self._assign_category_regions(categories_present)
            self._draw_category_regions()
        else:
            single_cat = list(categories_present.keys())[0]
            self._category_centers = {single_cat: QPointF(0, 0)}

        # ── Phase 2: Hierarchical layout per category ──────────────────
        positions: Dict[str, QPointF] = {}
        for cat, cat_nodes in categories_present.items():
            center = self._category_centers.get(cat, QPointF(0, 0))
            cat_positions = self._compute_hierarchical_layout(cat_nodes, edges, center)
            positions.update(cat_positions)

        # ── Phase 3: Force-directed refinement ─────────────────────────
        if len(nodes) > 1:
            positions = self._force_refinement(positions, nodes, edges, iterations=FORCE_ITERATIONS)

        return positions

    def _assign_category_regions(self, categories: Dict[str, List[Dict]]) -> Dict[str, QPointF]:
        """Place category centers in a circle."""
        cat_names = sorted(categories.keys())
        n = len(cat_names)
        centers: Dict[str, QPointF] = {}

        for i, cat in enumerate(cat_names):
            angle = 2 * math.pi * i / n - math.pi / 2  # start from top
            # Distance from center — tightly packed
            cat_count = len(categories[cat])
            spread = 150 + 10 * cat_count
            x = spread * math.cos(angle)
            y = spread * math.sin(angle)
            centers[cat] = QPointF(x, y)
        return centers

    def _draw_category_regions(self):
        """Draw semi-transparent background rectangles per category."""
        # Remove old regions
        for reg in self._category_regions.values():
            if reg.scene():
                self.scene.removeItem(reg)
        self._category_regions.clear()

        for cat, center in self._category_centers.items():
            # Count nodes in this category
            count = sum(1 for nd in self.nodes_data if nd.get("category") == cat)
            radius = CATEGORY_REGION_RADIUS_BASE * math.sqrt(max(count, 1) / 10)
            radius = max(150, min(radius, 600))
            region = CategoryRegion(cat, center, radius)
            self.scene.addItem(region)
            self._category_regions[cat] = region

    def _compute_hierarchical_layout(
        self, cat_nodes: List[Dict], all_edges: List[Dict], center: QPointF
    ) -> Dict[str, QPointF]:
        """
        Layered tree layout for one category cluster.
        Roots (no incoming subClassOf) at top, children below.
        """
        cat_uris = {n["uri"] for n in cat_nodes}

        # Build local children map for this category
        local_children: Dict[str, List[str]] = {}
        local_parents: Dict[str, str] = {}
        for ed in all_edges:
            if (
                ed["relation"] == "subClassOf"
                and ed["source"] in cat_uris
                and ed["target"] in cat_uris
            ):
                local_children.setdefault(ed["target"], []).append(ed["source"])
                local_parents[ed["source"]] = ed["target"]

        # Find roots: nodes with no incoming subClassOf within this category
        roots = [n["uri"] for n in cat_nodes if n["uri"] not in local_parents]
        # If no roots found (cycles or disconnected), treat all as roots
        if not roots:
            roots = [n["uri"] for n in cat_nodes]

        # BFS to assign layers
        layers: Dict[str, int] = {}
        queue: deque = deque()
        for r in roots:
            layers[r] = 0
            queue.append(r)

        while queue:
            current = queue.popleft()
            for child in local_children.get(current, []):
                new_layer = layers[current] + 1
                if child not in layers or new_layer < layers[child]:
                    layers[child] = new_layer
                    queue.append(child)

        # Assign layer 0 to any unvisited nodes
        for nd in cat_nodes:
            if nd["uri"] not in layers:
                layers[nd["uri"]] = 0

        # Group nodes by layer
        layer_groups: Dict[int, List[str]] = {}
        for uri, layer in layers.items():
            layer_groups.setdefault(layer, []).append(uri)

        # Position nodes
        positions: Dict[str, QPointF] = {}
        max_layer = max(layer_groups.keys()) if layer_groups else 0

        for layer_idx, uris_in_layer in layer_groups.items():
            n_in_layer = len(uris_in_layer)
            total_width = (n_in_layer - 1) * NODE_SPACING_X
            x_start = center.x() - total_width / 2
            y = center.y() + layer_idx * LAYER_SPACING_Y - (max_layer * LAYER_SPACING_Y / 2)

            for j, uri in enumerate(uris_in_layer):
                x = x_start + j * NODE_SPACING_X
                positions[uri] = QPointF(x, y)

        return positions

    def _force_refinement(
        self,
        positions: Dict[str, QPointF],
        nodes: List[Dict],
        edges: List[Dict],
        iterations: int = FORCE_ITERATIONS,
    ) -> Dict[str, QPointF]:
        """
        Light force-directed refinement with category center-gravity
        to resolve overlaps while preserving cluster structure.
        """
        # Convert to mutable format
        pos = {uri: (p.x(), p.y()) for uri, p in positions.items()}
        _node_uris = set(pos.keys())  # noqa: F841

        for _ in range(iterations):
            forces = {uri: (0.0, 0.0) for uri in pos}

            # Repulsion between all node pairs
            uris = list(pos.keys())
            for i in range(len(uris)):
                uri1 = uris[i]
                x1, y1 = pos[uri1]
                for j in range(i + 1, len(uris)):
                    uri2 = uris[j]
                    x2, y2 = pos[uri2]
                    dx = x1 - x2
                    dy = y1 - y2
                    dist_sq = dx * dx + dy * dy + 1
                    dist = math.sqrt(dist_sq)
                    force = FORCE_REPULSION / dist_sq
                    fx = force * dx / dist
                    fy = force * dy / dist
                    forces[uri1] = (forces[uri1][0] + fx, forces[uri1][1] + fy)
                    forces[uri2] = (forces[uri2][0] - fx, forces[uri2][1] - fy)

            # Attraction along edges
            for ed in edges:
                src = ed["source"]
                tgt = ed["target"]
                if src in pos and tgt in pos:
                    x1, y1 = pos[src]
                    x2, y2 = pos[tgt]
                    dx = x1 - x2
                    dy = y1 - y2
                    dist = math.sqrt(dx * dx + dy * dy + 1)
                    force = FORCE_ATTRACTION * (dist - FORCE_OPTIMAL_EDGE)
                    fx = force * dx / dist
                    fy = force * dy / dist
                    forces[src] = (forces[src][0] - fx, forces[src][1] - fy)
                    forces[tgt] = (forces[tgt][0] + fx, forces[tgt][1] + fy)

            # Center gravity per category
            for nd in nodes:
                uri = nd["uri"]
                if uri not in pos:
                    continue
                cat = nd.get("category", "default")
                center = self._category_centers.get(cat)
                if center:
                    cx, cy = center.x(), center.y()
                    x, y = pos[uri]
                    forces[uri] = (
                        forces[uri][0] + (cx - x) * FORCE_CENTER_GRAVITY,
                        forces[uri][1] + (cy - y) * FORCE_CENTER_GRAVITY,
                    )

            # Apply forces
            for uri in pos:
                x, y = pos[uri]
                fx, fy = forces[uri]
                pos[uri] = (x + fx * FORCE_DAMPING, y + fy * FORCE_DAMPING)

        return {uri: QPointF(x, y) for uri, (x, y) in pos.items()}
