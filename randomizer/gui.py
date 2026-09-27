"""DDS1 Randomizer — window (tkinter, shipped with Python; used by the Windows .exe).

Opened by `python -m randomizer` without arguments (or a double click on the .exe). The window only fills an
Options object, like a preset file or the command line, then calls generate(): same result for the same
seed and options, whatever the interface.
"""
import copy
import queue
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__
from .generate import generate, new_seed
from .options import Options

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:                                 # Linux without the Tk library
    tk = None

# (label shown, option value) for each choice list
CHOICES = {
    "enemy_skills": [("Adapted to their new level", "adapt"), ("Random (same type and rank)", "random"),
                     ("Original", "original")],
    "affinities": [("Shuffled", "shuffle"), ("Random", "random"), ("Original", "original")],
    "boss_hp": [("Level curve (a tough boss stays tough)", "curve"), ("HP of the boss it replaces (easier)", "place")],
    "unique_skills": [("Kept as they are", "keep"), ("Scaled to the new level (easier)", "power")],
    "mantras": [("Similar level", "tiered"), ("Fully random", "random"), ("Original", "original")],
    "chests": [("Shuffled", "shuffle"), ("Random", "random"), ("Original", "original")],
    "shops": [("Similar value", "tiered"), ("Random", "random"), ("Original", "original")],
}


class App:
    def __init__(self, root: "tk.Tk"):
        self.root = root
        self.base = Options()                       # preset loaded (keeps the options without a widget)
        self.messages: queue.Queue = queue.Queue()
        self.spoiler: Path | None = None
        root.title(f"DDS1 Randomizer {__version__}")
        root.minsize(640, 560)
        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        # --- files and seed ---
        self.src = tk.StringVar()
        self.dst = tk.StringVar()
        self.seed = tk.StringVar(value=str(new_seed()))
        self._file_row(main, 0, "Original ISO", self.src, self._pick_src)
        self._file_row(main, 1, "Randomized ISO", self.dst, self._pick_dst)
        ttk.Label(main, text="Seed").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(main, textvariable=self.seed).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Button(main, text="New seed", command=lambda: self.seed.set(str(new_seed()))).grid(
            row=2, column=2, sticky="ew", padx=(6, 0), pady=2)

        # --- options ---
        box = ttk.LabelFrame(main, text="Options", padding=8)
        box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        box.columnconfigure(1, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        r = 0
        for key, text in (("enemies_shuffle", "Shuffle enemies of random battles"),
                          ("enemies_scaling", "Rescale them to the level of the area")):
            self._check(box, r, key, text)
            r += 1
        for key, text in (("enemy_skills", "Enemy skills"), ("affinities", "Enemy affinities")):
            self._combo(box, r, key, text)
            r += 1
        self._check(box, r, "protect_physical", "Enemies are never immune to physical attacks")
        r += 1
        self._check(box, r, "bosses_shuffle", "Shuffle bosses")
        r += 1
        for key, text in (("boss_hp", "Boss HP"), ("unique_skills", "Boss signature skills"),
                          ("mantras", "Mantras"), ("chests", "Chests"), ("shops", "Shops")):
            self._combo(box, r, key, text)
            r += 1
        self._check(box, r, "heal_guarantee", "Dia and Media available early")
        r += 1
        self._check(box, r, "verify_iso", "Also check the whole ISO (slower)")
        self._show(self.base)

        # --- actions and log ---
        bar = ttk.Frame(main)
        bar.grid(row=4, column=0, columnspan=3, sticky="ew")
        ttk.Button(bar, text="Load preset…", command=self._load_preset).pack(side="left")
        self.open_btn = ttk.Button(bar, text="Open spoiler log", command=self._open_spoiler, state="disabled")
        self.open_btn.pack(side="left", padx=6)
        self.go = ttk.Button(bar, text="Randomize!", command=self._start)
        self.go.pack(side="right")
        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=6)
        self.log = tk.Text(main, height=8, wrap="word", state="disabled")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew")
        main.rowconfigure(6, weight=1)
        self._write("Choose your original ISO (NTSC-U, SLUS-20974). It is never modified.")

    # --- widgets ---
    def _file_row(self, parent, row: int, text: str, var, command) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=2)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, sticky="ew", padx=(6, 0), pady=2)

    def _check(self, parent, row: int, key: str, text: str) -> None:
        self.vars[key] = tk.BooleanVar()
        ttk.Checkbutton(parent, text=text, variable=self.vars[key]).grid(row=row, column=0, columnspan=2, sticky="w")

    def _combo(self, parent, row: int, key: str, text: str) -> None:
        self.vars[key] = tk.StringVar()
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 10))
        ttk.Combobox(parent, textvariable=self.vars[key], state="readonly",
                     values=[label for label, _ in CHOICES[key]]).grid(row=row, column=1, sticky="ew", pady=1)

    # --- options <-> widgets ---
    def _show(self, o: Options) -> None:
        label = {key: {v: l for l, v in pairs} for key, pairs in CHOICES.items()}
        v = self.vars
        v["enemies_shuffle"].set(o.enemies.shuffle)
        v["enemies_scaling"].set(o.enemies.scaling)
        v["enemy_skills"].set(label["enemy_skills"][o.enemy_skills.mode])
        v["affinities"].set(label["affinities"][o.affinities.mode])
        v["protect_physical"].set(o.affinities.protect_physical)
        v["bosses_shuffle"].set(o.bosses.shuffle)
        v["boss_hp"].set(label["boss_hp"][o.bosses.hp])
        v["unique_skills"].set(label["unique_skills"][o.bosses.unique_skills])
        v["mantras"].set(label["mantras"][o.mantras.mode])
        v["heal_guarantee"].set(o.mantras.guarantee_heal and o.mantras.guarantee_group_heal)
        v["chests"].set(label["chests"][o.chests.mode])
        v["shops"].set(label["shops"][o.shops.mode])

    def options(self) -> Options:
        value = {key: dict(pairs) for key, pairs in CHOICES.items()}
        v = self.vars
        o = copy.deepcopy(self.base)
        o.enemies.shuffle = v["enemies_shuffle"].get()
        o.enemies.scaling = v["enemies_scaling"].get()
        o.enemy_skills.mode = value["enemy_skills"][v["enemy_skills"].get()]
        o.affinities.mode = value["affinities"][v["affinities"].get()]
        o.affinities.protect_physical = v["protect_physical"].get()
        o.bosses.shuffle = v["bosses_shuffle"].get()
        o.bosses.hp = value["boss_hp"][v["boss_hp"].get()]
        o.bosses.unique_skills = value["unique_skills"][v["unique_skills"].get()]
        o.mantras.mode = value["mantras"][v["mantras"].get()]
        o.mantras.guarantee_heal = o.mantras.guarantee_group_heal = v["heal_guarantee"].get()
        o.chests.mode = value["chests"][v["chests"].get()]
        o.shops.mode = value["shops"][v["shops"].get()]
        return o

    # --- actions ---
    def _pick_src(self) -> None:
        path = filedialog.askopenfilename(title="Original ISO", filetypes=[("ISO image", "*.iso *.ISO"), ("All files", "*")])
        if path:
            self.src.set(path)
            if not self.dst.get():
                p = Path(path)
                self.dst.set(str(p.with_name(f"{p.stem}_randomized.iso")))

    def _pick_dst(self) -> None:
        path = filedialog.asksaveasfilename(title="Randomized ISO", defaultextension=".iso",
                                            filetypes=[("ISO image", "*.iso")])
        if path:
            self.dst.set(path)

    def _load_preset(self) -> None:
        path = filedialog.askopenfilename(title="Preset", filetypes=[("Preset", "*.toml"), ("All files", "*")])
        if not path:
            return
        try:
            self.base = Options.from_toml(Path(path))
        except (ValueError, OSError) as e:
            messagebox.showerror("Preset", str(e))
            return
        self._show(self.base)
        self._write(f"Preset loaded: {path}")

    def _start(self) -> None:
        try:
            seed = int(self.seed.get().strip())
            if not 0 <= seed < 1 << 32:
                raise ValueError
        except ValueError:
            messagebox.showerror("Seed", "The seed must be a whole number between 0 and 4294967295.")
            return
        if not self.src.get() or not self.dst.get():
            messagebox.showerror("Files", "Choose the original ISO and the randomized ISO to create.")
            return
        src, dst, opts, verify = Path(self.src.get()), Path(self.dst.get()), self.options(), self.vars["verify_iso"].get()
        self.go.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress.start(12)
        self._write(f"--- seed {seed} ---")
        threading.Thread(target=self._run, args=(src, dst, seed, opts, verify), daemon=True).start()
        self.root.after(100, self._poll)

    def _run(self, src: Path, dst: Path, seed: int, opts: Options, verify: bool) -> None:
        try:
            spoiler = generate(src, dst, seed, opts, verify, log=lambda m: self.messages.put(("log", m)))
            self.messages.put(("done", spoiler))
        except (ValueError, OSError) as e:
            self.messages.put(("error", str(e)))
        except Exception as e:                       # unexpected: shown instead of a silent failure
            self.messages.put(("error", f"unexpected error: {e!r}"))

    def _poll(self) -> None:
        while not self.messages.empty():
            kind, payload = self.messages.get()
            if kind == "log":
                self._write(payload)
                continue
            self.progress.stop()
            self.go.configure(state="normal")
            if kind == "done":
                self.spoiler = payload
                self.open_btn.configure(state="normal")
                self._write("Done! Boot the randomized ISO in your emulator (a memory card save works).")
                messagebox.showinfo("DDS1 Randomizer", "Randomized ISO created.")
            else:
                self._write(f"Error: {payload}")
                messagebox.showerror("DDS1 Randomizer", payload)
            return
        self.root.after(100, self._poll)

    def _open_spoiler(self) -> None:
        if not self.spoiler:
            return
        if sys.platform == "win32":
            import os
            os.startfile(self.spoiler)               # noqa: S606 (opens the text file in the default editor)
        else:
            subprocess.Popen(["xdg-open", str(self.spoiler)])

    def _write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    if tk is None:
        sys.exit("The window needs the Tk library (Linux: install the 'tk' package), "
                 "or use the command line: python -m randomizer --help")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
