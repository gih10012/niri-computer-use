#include <QApplication>
#include <QWidget>
#include <QVBoxLayout>
#include <QLineEdit>
#include <QTextEdit>
#include <QPushButton>
#include <QCheckBox>
#include <QTimer>
#include <QSaveFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTextCursor>

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setDesktopFileName("niri-cu-qt-probe");
    if (argc != 2) return 2;
    const QString statePath = QString::fromLocal8Bit(argv[1]);
    QWidget window;
    window.setWindowTitle("niri Computer Use Qt probe");
    auto layout = new QVBoxLayout(&window);
    QLineEdit entry;
    entry.setAccessibleName("Probe text");
    QTextEdit rich;
    rich.setAccessibleName("Probe rich");
    QPushButton counter("Probe counter");
    QCheckBox check("Probe checkbox");
    layout->addWidget(&entry);
    layout->addWidget(&rich);
    layout->addWidget(&counter);
    layout->addWidget(&check);
    int clicks = 0;
    QObject::connect(&counter, &QPushButton::clicked, [&]{ ++clicks; });
    QTimer timer;
    QObject::connect(&timer, &QTimer::timeout, [&]{
        QTextCursor cursor(rich.document());
        cursor.setPosition(0);
        cursor.movePosition(QTextCursor::NextCharacter, QTextCursor::KeepAnchor);
        QJsonObject state {
            {"text", entry.text()},
            {"selected", entry.selectedText()},
            {"clicks", clicks},
            {"checked", check.isChecked()},
            {"rich", rich.toPlainText()},
            {"bold", cursor.charFormat().fontWeight() >= QFont::Bold}
        };
        QSaveFile output(statePath);
        if (output.open(QIODevice::WriteOnly)) { output.write(QJsonDocument(state).toJson()); output.commit(); }
    });
    timer.start(40);
    window.resize(700, 600);
    window.show();
    entry.setFocus();
    return app.exec();
}
