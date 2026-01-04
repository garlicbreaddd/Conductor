import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QLabel, QPushButton
from PyQt6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("testapp")
        
        centralwidget = QWidget()
        self.setCentralWidget(centralwidget)
        self.setMinimumWidth(1200)
        self.setMinimumHeight(800)

        # create widgets
        self.label = QLabel("Test")
        self.label2 = QLabel("Test2")
        self.simview = QGraphicsView()
        self.sidebar1 = QWidget()
        self.sidebar2 = QWidget()
        sidebar1lay = QVBoxLayout()
        sidebar2lay = QVBoxLayout()
        self.btn1 = QPushButton("<", self.simview)
        self.btn2 = QPushButton(">", self.simview)


        sidebar1lay.addWidget(self.label)
        self.sidebar1.setLayout(sidebar1lay)
        sidebar2lay.addWidget(self.label2)
        self.sidebar2.setLayout(sidebar2lay)


        mainlay = QHBoxLayout()
        mainlay.addWidget(self.sidebar1)
        mainlay.addWidget(self.simview)
        mainlay.addWidget(self.sidebar2)

        centralwidget.setLayout(mainlay)


        self.btn1.clicked.connect(self.toggleSidebar1)
        self.btn2.clicked.connect(self.toggleSidebar2)
        self.sidebar1.hide()
        self.sidebar2.hide()


    def toggleSidebar1(self):
        if not self.sidebar1.isHidden():
            self.sidebar1.hide()
            QTimer.singleShot(0, self.updateBtn2Pos)
        else:
            self.sidebar1.show()
            self.updateBtn2Pos()
    def toggleSidebar2(self):
        if not self.sidebar2.isHidden():
            self.sidebar2.hide()
            QTimer.singleShot(0, self.updateBtn2Pos)
        else:
            self.sidebar2.show()
            self.updateBtn2Pos()

    # move the stupid right button to correct position at both start and loop
    def showEvent(self,event):
        super().showEvent(event)
        self.updateBtn2Pos()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.updateBtn2Pos()
    def updateBtn2Pos(self):
        self.btn2.move(self.simview.width() - self.btn1.width(), 0)




    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()

