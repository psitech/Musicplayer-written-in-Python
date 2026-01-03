import threading
import pygame
from pathlib import Path
from mutagen import File

# ADD PYQT6 IMPORTS
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QListWidget, QFrame,
    QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal # Import pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent # Import QKeyEvent

# initialize Pygame mixer
pygame.mixer.init()

class MusicPlayer(QMainWindow):
    # Define a custom signal to communicate scan completion from worker thread to GUI thread
    scan_completed_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        # Window Setup (1280x720)
        self.setWindowTitle("MusicPlayer")
        self.setGeometry(100, 100, 1280, 720)
        # ctk.set_appearance_mode("dark") # REMOVE - Requires stylesheets in PyQt6

        # State variables
        self.music_files = []
        self.current_index = -1
        self.is_paused = False
        self.song_length = 0
        self.is_playing = False
        self.seek_offset = 0 # tracks absolute position for the seek bar
        self.is_seeking_by_user = False # New flag to track if user is dragging slider

        # Search state variables
        self.last_query = ""
        self.last_search_index = -1

        # Key bindings (REMOVED - needs PyQt6 key event handling)
        # self.bind("<F3>", self.trigger_search)
        # self.bind("<F4>", self.find_next_search)
        # self.bind("<space>", self.toggle_play)
        # self.bind("<Up>", self.prev_track)
        # self.bind("<Down>", self.next_track)

        # Create a central widget for QMainWindow
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Playlist Area
        self.list_frame = QFrame()
        self.list_layout = QHBoxLayout(self.list_frame)
        self.main_layout.addWidget(self.list_frame)

        self.playlist = QListWidget()
        self.playlist.setFont(QFont("Segoe UI", 11))
        self.playlist.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # Apply stylesheet to reduce item spacing
        self.playlist.setStyleSheet("QListWidget::item { padding: 0px; margin: 0px; min-height: 15px; }")
        self.playlist.setSpacing(0) # Also set spacing between items to 0
        self.list_layout.addWidget(self.playlist)

        # QListWidget has built-in scrollbars, so explicit QScrollbar is often not needed.

        # Seek Bar (Slider) and Time Labels
        self.progress_frame = QWidget()
        self.progress_layout = QHBoxLayout(self.progress_frame)
        self.main_layout.addWidget(self.progress_frame)

        self.current_time_label = QLabel("00:00")
        self.current_time_label.setFont(QFont("Segoe UI", 12))
        self.progress_layout.addWidget(self.current_time_label)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 100)
        self.seek_slider.setValue(0)
        self.seek_slider.setContentsMargins(10, 0, 10, 0) # Adjust padding
        # Connect slider signals
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released) # Connect to the handling method
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Prevent slider from taking focus and handling arrow keys
        self.progress_layout.addWidget(self.seek_slider)

        self.total_time_label = QLabel("00:00")
        self.total_time_label.setFont(QFont("Segoe UI", 12))
        self.progress_layout.addWidget(self.total_time_label)

        # Control Panel
        self.controls_frame = QFrame()
        self.controls_layout = QGridLayout(self.controls_frame)
        self.main_layout.addWidget(self.controls_frame)

        # Helper function to create buttons with common styling
        def create_button(text, command):
            btn = QPushButton(text)
            btn.setFixedHeight(40)
            btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            btn.clicked.connect(command)
            return btn

        self.btn_open = create_button("Open music folder", self.start_folder_scan)
        self.controls_layout.addWidget(self.btn_open, 0, 0, 1, 1) # span 1 column

        self.btn_prev = create_button("PREV", self.prev_track)
        self.btn_prev.setFixedWidth(100)
        self.controls_layout.addWidget(self.btn_prev, 0, 2)

        self.btn_play = create_button("PLAY/PAUSE", self.toggle_play)
        self.controls_layout.addWidget(self.btn_play, 0, 3)

        self.btn_stop = create_button("STOP", self.stop_music)
        self.btn_stop.setFixedWidth(100)
        self.controls_layout.addWidget(self.btn_stop, 0, 4)

        self.btn_next = create_button("NEXT", self.next_track)
        self.btn_next.setFixedWidth(100)
        self.controls_layout.addWidget(self.btn_next, 0, 5)

        self.status_label = QLabel("0 tracks loaded")
        self.status_label.setFont(QFont("Segoe UI", 12))
        self.controls_layout.addWidget(self.status_label, 0, 6, 1, 2, Qt.AlignmentFlag.AlignRight)

        # Adjust column weights in QGridLayout
        self.controls_layout.setColumnStretch(1, 1)
        self.controls_layout.setColumnStretch(6, 1)

        # Connect the custom signal to the finalize_scan method
        self.scan_completed_signal.connect(self.finalize_scan)

        # start background monitor for playback and auto-next using QTimer
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.monitor_playback)
        self.playback_timer.start(500)

    def keyPressEvent(self, event: QKeyEvent):
        # Override keyPressEvent for custom key bindings
        if event.key() == Qt.Key.Key_F3:
            self.trigger_search()
        elif event.key() == Qt.Key.Key_F4:
            self.find_next_search()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key.Key_Up:
            self.prev_track()
        elif event.key() == Qt.Key.Key_Down:
            self.next_track()
        else:
            super().keyPressEvent(event) # Call base class method for other key events

    def _on_slider_pressed(self):
        """Set a flag when the user starts dragging the slider."""
        self.is_seeking_by_user = True

    def _on_slider_released(self):
        """Reset the flag and perform the seek when the user releases the slider."""
        self.is_seeking_by_user = False
        if self.is_playing: # and not self.is_paused: # seeking should work even when paused
            value = self.seek_slider.value() # Get the current slider value
            self.seek_offset = value # value from QSlider is already the desired position
            pygame.mixer.music.play(start=value)
            if self.is_paused:
                pygame.mixer.music.pause()

    def monitor_playback(self):
        if self.is_playing and not self.is_paused:
            # Only update the slider if the user is not currently dragging it
            if not self.is_seeking_by_user:
                relative_pos = pygame.mixer.music.get_pos() / 1000

                if relative_pos == -1:
                    self.next_track()
                else:
                    current_actual_time = relative_pos + self.seek_offset
                    if self.song_length > 0 and current_actual_time >= self.song_length - 0.5:
                        self.next_track()
                    elif self.song_length > 0:
                        self.seek_slider.setValue(int(current_actual_time))
                        self.current_time_label.setText(self.format_time(current_actual_time))

    def trigger_search(self):
        query, ok = QInputDialog.getText(self, "Find Music", "Search for a track or folder:")
        if ok and query:
            self.last_query = query.lower()
            self.last_search_index = -1
            self.find_next_search()

    def find_next_search(self):
        if not self.last_query: return
        all_tracks = [self.playlist.item(i).text() for i in range(self.playlist.count())]
        num_tracks = len(all_tracks)
        start_index = self.last_search_index + 1
        for i in range(num_tracks):
            idx = (start_index + i) % num_tracks
            if self.last_query in all_tracks[idx].lower():
                self.last_search_index = idx
                self.playlist.clearSelection()
                self.playlist.setCurrentRow(idx)
                self.playlist.scrollToItem(self.playlist.item(idx))
                return

    def start_folder_scan(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            self.btn_open.setEnabled(False)
            self.btn_open.setText("Scanning...")
            self.music_files = []
            self.playlist.clear()
            threading.Thread(target=self.scan_logic, args=(folder_path,), daemon=True).start()

    def scan_logic(self, folder_path):
        extensions = ('.mp3', '.wav', '.flac')
        temp_data = []
        base_path = Path(folder_path)
        for path in base_path.rglob('*'):
            if path.suffix.lower() in extensions:
                try:
                    display_name = str(path.relative_to(base_path))
                    temp_data.append((str(path), display_name))
                except Exception:
                    temp_data.append((str(path), path.name))

        temp_data.sort(key=lambda x: x[1].lower())
        self.scan_completed_signal.emit(temp_data)

    def finalize_scan(self, found_data):
        for full_path, display_name in found_data:
            self.music_files.append(full_path)
            self.playlist.addItem(display_name)
        if self.music_files:
            self.current_index = 0
            self.playlist.setCurrentRow(0)
        self.btn_open.setEnabled(True)
        self.btn_open.setText("Open music folder")
        self.status_label.setText(f"{len(self.music_files)} tracks loaded")

    def format_time(self, seconds):
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def play_track(self, index=None):
        try:
            if index is not None:
                self.current_index = index
            else:
                selected_items = self.playlist.selectedItems()
                if selected_items:
                    self.current_index = self.playlist.row(selected_items[0])
                elif self.playlist.count() > 0: # If no explicit selection, but there are songs, play the first one
                    self.current_index = 0
                else:
                    return # No music to play

            if 0 <= self.current_index < len(self.music_files):
                track_path = self.music_files[self.current_index]
                audio = File(track_path)
                self.song_length = audio.info.length

                self.seek_offset = 0
                self.seek_slider.setRange(0, int(self.song_length))
                self.seek_slider.setValue(0)
                self.total_time_label.setText(self.format_time(self.song_length))

                pygame.mixer.music.load(track_path)
                pygame.mixer.music.play()
                self.is_playing, self.is_paused = True, False

                self.playlist.clearSelection()
                self.playlist.setCurrentRow(self.current_index)
                self.playlist.scrollToItem(self.playlist.item(self.current_index))

        except Exception as e:
            print(f"Playback error: {e}")

    def toggle_play(self):
        if not self.music_files: return

        if self.is_playing and not self.is_paused:
            pygame.mixer.music.pause()
            self.is_paused = True
        elif self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
        else:
            # If nothing is playing, initiate playback based on selection or default to first track.
            self.play_track()

    def stop_music(self):
        pygame.mixer.music.stop()
        self.is_playing, self.is_paused = False, False
        self.seek_offset = 0
        self.seek_slider.setValue(0)
        self.current_time_label.setText("00:00")

    def next_track(self):
        if self.music_files:
            new_idx = (self.current_index + 1) % len(self.music_files)
            self.play_track(index=new_idx)
        # After changing track, ensure play button has focus for spacebar to work
        self.btn_play.setFocus()

    def prev_track(self):
        if self.music_files:
            new_idx = (self.current_index - 1) % len(self.music_files)
            self.play_track(index=new_idx)
        # After changing track, ensure play button has focus for spacebar to work
        self.btn_play.setFocus()

if __name__ == "__main__":
    app_qt = QApplication([])
    # Dark theme stylesheet
    dark_stylesheet = """
        QMainWindow {
            background-color: #2e2e2e;
        }
        QWidget {
            background-color: #3c3c3c;
            color: #f0f0f0;
        }
        QLabel {
            color: #f0f0f0;
        }
        QPushButton {
            background-color: #555555;
            color: #f0f0f0;
            border: 1px solid #777777;
            padding: 5px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #666666;
        }
        QPushButton:pressed {
            background-color: #444444;
        }
        QSlider::groove:horizontal {
            border: 1px solid #999999;
            height: 8px;
            background: #2e2e2e;
            margin: 2px 0;
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background: #f0f0f0;
            border: 1px solid #777777;
            width: 18px;
            margin: -2px 0px; 
            border-radius: 9px;
        }
        QListWidget {
            background-color: #2e2e2e;
            color: #f0f0f0;
            border: 1px solid #555555;
            selection-background-color: #555555;
            selection-color: #f0f0f0;
        }
        QListWidget::item:selected {
            background-color: #555555;
            color: #f0f0f0;
        }
        QInputDialog {
            background-color: #3c3c3c;
            color: #f0f0f0;
        }
        QLineEdit {
            background-color: #555555;
            color: #f0f0f0;
            border: 1px solid #777777;
            padding: 3px;
        }
    """
    app_qt.setStyleSheet(dark_stylesheet)

    app = MusicPlayer()
    app.show()
    app_qt.exec()