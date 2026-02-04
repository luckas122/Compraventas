from PyQt5.QtCore import Qt, QSize, QEvent, QObject, QRect,QSortFilterProxyModel, QModelIndex,QTimer,QSignalBlocker,QStringListModel,QDate,QTime


class LimitedFilterProxy(QSortFilterProxyModel):
    def __init__(self, limit=30, parent=None):
        super().__init__(parent)
        self._limit = int(limit)

    def rowCount(self, parent=QModelIndex()):
        rc = super().rowCount(parent)
        return min(rc, self._limit)