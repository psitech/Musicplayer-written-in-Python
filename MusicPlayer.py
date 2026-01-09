# python 3.13.9, pygame 2.6.1, pygame-ce 2.5.6, SDL 2.32.10, customtkinter 5.2.2, mutagen 1.47.0
import threading
import customtkinter as ctk
import pygame
from tkinter import filedialog, Listbox, END, SINGLE
from pathlib import Path
from mutagen import File

# initialize Pygame mixer
pygame.init()

class MusicPlayer(ctk.CTk):
    SONG_END = pygame.USEREVENT + 1 # Define custom event for song end

    def __init__(self):
        super().__init__()

        # Window Setup (1280x720)
        self.title("MusicPlayer")
        self.geometry("1280x720")
        ctk.set_appearance_mode("dark")

        # State variables
        self.music_files = []
        self.current_index = -1
        self.is_paused = False
        self.song_length = 0
        self.is_playing = False
        self.seek_offset = 0 # tracks absolute position for the seek bar

        # Search state variables
        self.last_query = ""
        self.last_search_index = -1

        # Key bindings
        self.bind("<F3>", self.trigger_search)
        self.bind("<F4>", self.find_next_search)
        self.bind("<space>", self.toggle_play)
        self.bind("<Up>", self.prev_track)
        self.bind("<Down>", self.next_track)

        # Main Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main Container
        self.main_container = ctk.CTkFrame(self, corner_radius=20)
        self.main_container.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # Playlist Area
        self.list_frame = ctk.CTkFrame(self.main_container, corner_radius=15, fg_color="#1a1a1a")
        self.list_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.playlist = Listbox(self.list_frame, bg="#1a1a1a", fg="#ffffff",
                                selectbackground="#1f538d", borderwidth=0,
                                highlightthickness=0, font=("Segoe UI", 12),
                                selectmode=SINGLE, activestyle="none",
                                exportselection=False)
        self.playlist.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        # Bind double-click event to play selected track
        self.playlist.bind("<Double-1>", self.play_selected_track_on_double_click)

        self.scrollbar = ctk.CTkScrollbar(self.list_frame, command=self.playlist.yview)
        self.scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        self.playlist.config(yscrollcommand=self.scrollbar.set)

        # Seek Bar (Slider) and Time Labels
        self.progress_frame = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="transparent")
        self.progress_frame.grid(row=1, column=0, padx=10, pady=(0, 20), sticky="ew")

        self.current_time_label = ctk.CTkLabel(self.progress_frame, text="00:00", font=("Segoe UI", 14))
        self.current_time_label.pack(side="left", padx=5)

        self.seek_slider = ctk.CTkSlider(self.progress_frame, from_=0, to=100, height=16, command=self.slider_event)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10)

        self.total_time_label = ctk.CTkLabel(self.progress_frame, text="00:00", font=("Segoe UI", 14))
        self.total_time_label.pack(side="right", padx=5)

        # Control Panel
        self.controls_frame = ctk.CTkFrame(self.main_container, corner_radius=15)
        self.controls_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.controls_frame.grid_columnconfigure(1, weight=1)
        self.controls_frame.grid_columnconfigure(6, weight=1)

        btn_style = {"corner_radius": 40, "height": 40, "font": ("Segoe UI", 14, "bold")}

        self.btn_open = ctk.CTkButton(self.controls_frame, text="Open music folder", command=self.start_folder_scan, **btn_style)
        self.btn_open.grid(row=0, column=0, padx=10, pady=10)

        self.btn_prev = ctk.CTkButton(self.controls_frame, text="PREV", width=100, command=self.prev_track, **btn_style)
        self.btn_prev.grid(row=0, column=2, padx=5, pady=10)

        self.btn_play = ctk.CTkButton(self.controls_frame, text="PLAY/PAUSE", command=self.toggle_play, **btn_style)
        self.btn_play.grid(row=0, column=3, padx=5, pady=10)

        self.btn_stop = ctk.CTkButton(self.controls_frame, text="STOP", width=100, command=self.stop_music, **btn_style)
        self.btn_stop.grid(row=0, column=4, padx=5, pady=10)

        self.btn_next = ctk.CTkButton(self.controls_frame, text="NEXT", width=100, command=self.next_track, **btn_style)
        self.btn_next.grid(row=0, column=5, padx=5, pady=10)

        self.status_label = ctk.CTkLabel(self.controls_frame, text="0 tracks loaded", font=("Segoe UI", 14))
        self.status_label.grid(row=0, column=7, padx=10, pady=10, sticky="e")

        # start background monitor for playback and auto-next
        self.monitor_playback()
        self.after(100, self.check_pygame_events) # Start checking for pygame events

    def slider_event(self, value): # handles user-controlled seeking
        if self.is_playing:
            self.seek_offset = value
            pygame.mixer.music.play(start=value)
            if self.is_paused:
                pygame.mixer.music.pause()

    def monitor_playback(self): # stable updates for seek bar position
        if self.is_playing and not self.is_paused:
            relative_pos = pygame.mixer.music.get_pos() / 1000
            current_actual_time = relative_pos + self.seek_offset
            if self.song_length > 0 and current_actual_time >= 0:
                self.seek_slider.set(current_actual_time)
                self.current_time_label.configure(text=self.format_time(current_actual_time))

        self.after(250, self.monitor_playback)

    def check_pygame_events(self): # New method to handle pygame events
        for event in pygame.event.get():
            if event.type == self.SONG_END:
                self.next_track()
                break # Process only one SONG_END event per check
        self.after(100, self.check_pygame_events) # Schedule next check

    def trigger_search(self, event=None): # F3 search functionality
        dialog = ctk.CTkInputDialog(text="Search for a track or folder:", title="Find Music")
        query = dialog.get_input()
        if query:
            self.last_query = query.lower()
            self.last_search_index = -1
            self.find_next_search()

    def find_next_search(self, event=None): # F4 cyclic search functionality
        if not self.last_query: return
        all_tracks = self.playlist.get(0, END)
        num_tracks = len(all_tracks)
        start_index = self.last_search_index + 1
        for i in range(num_tracks):
            idx = (start_index + i) % num_tracks
            if self.last_query in all_tracks[idx].lower():
                self.last_search_index = idx
                self.playlist.selection_clear(0, END)
                self.playlist.selection_set(idx)
                self.playlist.activate(idx)
                self.playlist.see(idx)
                return

    def start_folder_scan(self): # launches threaded recursive scanner
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.btn_open.configure(state="disabled", text="Scanning...")
            self.music_files = []
            self.playlist.delete(0, END)
            threading.Thread(target=self.scan_logic, args=(folder_path,), daemon=True).start()

    def scan_logic(self, folder_path): # recursive scan with alphabetical sorting by display path
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

        # sort using the second element (display name) of the tuple
        temp_data.sort(key=self.get_display_name_lower)
        self.after(0, self.finalize_scan, temp_data)

    def get_display_name_lower(self, item):
        return item[1].lower()

    def finalize_scan(self, found_data):
        for full_path, display_name in found_data:
            self.music_files.append(full_path)
            self.playlist.insert(END, display_name)
        if self.music_files:
            self.current_index = 0
            self.playlist.selection_set(0)
        self.btn_open.configure(state="normal", text="Open music folder")
        self.status_label.configure(text=f"{len(self.music_files)} tracks loaded")

    def format_time(self, seconds):
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def play_selected_track_on_double_click(self, event):
        selected_indices = self.playlist.curselection()
        if selected_indices:
            index = selected_indices[0]
            self.play_track(index=index)

    def play_track(self, index=None):
        try:
            selection = None # initialize selection to None so it always exists in this scope

            if index is not None:
                self.current_index = index
            else:
                selection = self.playlist.curselection()
                if selection:
                    self.current_index = selection[0]
                else:
                    return # exit if nothing is selected and no index provided

            if 0 <= self.current_index < len(self.music_files):
                track_path = self.music_files[self.current_index]
                audio = File(track_path)
                self.song_length = audio.info.length

                # reset seek variables
                self.seek_offset = 0
                self.seek_slider.configure(from_=0, to=self.song_length)
                self.seek_slider.set(0)
                self.total_time_label.configure(text=self.format_time(self.song_length))

                pygame.mixer.music.load(track_path)
                pygame.mixer.music.play()
                pygame.mixer.music.set_endevent(self.SONG_END)    # Set the custom end event
                self.is_playing, self.is_paused = True, False

                self.playlist.selection_clear(0, END)             # clear all current selections
                self.playlist.selection_set(self.current_index)   # select the new track
                self.playlist.activate(self.current_index)        # set focus anchor to new track
                self.playlist.see(self.current_index)             # auto-scroll if off-screen

        except Exception as e:
            print(f"Playback error: {e}")

    def toggle_play(self, event=None):
        if not self.music_files: return
        if self.is_playing and not self.is_paused:
            pygame.mixer.music.pause()
            self.is_paused = True
        elif self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
        else:
            self.play_track()

    def stop_music(self):
        pygame.mixer.music.stop()
        self.is_playing, self.is_paused = False, False
        self.seek_offset = 0
        self.seek_slider.set(0)
        self.current_time_label.configure(text="00:00")

    def next_track(self, event=None):
        if self.music_files:
            new_idx = (self.current_index + 1) % len(self.music_files)
            self.play_track(index=new_idx)

    def prev_track(self, event=None):
        if self.music_files:
            new_idx = (self.current_index - 1) % len(self.music_files)
            self.play_track(index=new_idx)

if __name__ == "__main__":
    app = MusicPlayer()
    app.mainloop()
