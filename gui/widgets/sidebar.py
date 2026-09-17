"""
Sidebar navigation widget for the ISA Data Steward GUI.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    """Sidebar navigation widget with navigation buttons."""

    # Signal emitted when a navigation item is clicked
    navigationRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.button_group = QButtonGroup(self)
        self.current_page = "dashboard"
        self.setup_ui()

    def setup_ui(self):
        """Set up sidebar UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from utils.config_loader import get_profile

        sidebar_title = get_profile().get_namespace_prefix().upper() or "ISA Steward"
        # App title
        title_label = QLabel(sidebar_title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("sidebarTitle")
        layout.addWidget(title_label)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #34495e; max-height: 1px;")
        layout.addWidget(divider)

        # Scroll area for navigation buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 10, 0, 10)
        scroll_layout.setSpacing(2)

        # Navigation items - using PyQt6 standard icons
        style = self.style()
        nav_items = [
            (
                "dashboard",
                "Dashboard",
                style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            ),
            ("studies", "Studies", style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)),
            (
                "process_sequence",
                "Process Sequence",
                style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            ),
            (
                "materials",
                "Materials",
                style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            ),
            (
                "assays",
                "Assays",
                style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ),
            ("files", "Files", style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)),
            (
                "ontology",
                "Ontology Browser",
                style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            ),
            (
                "templates",
                "Templates",
                style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ),
            (
                "settings",
                "Settings",
                style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ),
        ]

        for page_id, label, icon in nav_items:
            btn = self._create_nav_button(page_id, label, icon)
            self.button_group.addButton(btn)
            scroll_layout.addWidget(btn)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def _create_nav_button(self, page_id: str, label: str, icon: QIcon) -> QPushButton:
        """Create a navigation button."""
        btn = QPushButton(label)
        btn.setObjectName("sidebarButton")
        btn.setCheckable(True)
        btn.setProperty("pageId", page_id)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(icon)
        icon_size = QSize(24, 24)
        btn.setIconSize(icon_size)

        if page_id == self.current_page:
            btn.setChecked(True)

        btn.clicked.connect(lambda: self._on_nav_clicked(page_id))
        return btn

    def _on_nav_clicked(self, page_id: str):
        """Handle navigation button click."""
        self.current_page = page_id
        self.navigationRequested.emit(page_id)

    def set_current_page(self, page_id: str):
        """Set the current active page."""
        self.current_page = page_id
        for btn in self.button_group.buttons():
            if btn.property("pageId") == page_id:
                btn.setChecked(True)
                break
