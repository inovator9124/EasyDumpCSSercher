#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Поиск строк в dump.cs — GUI (Tkinter)
"""

import re
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# ---------- ЯДРО ПОИСКА ----------

def read_file(path: Path):
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            with path.open("r", encoding=enc, errors="strict") as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def search_plain(lines, patterns, case_sensitive):
    if not case_sensitive:
        patterns = [p.lower() for p in patterns]
    out = []
    for i, line in enumerate(lines, 1):
        h = line if case_sensitive else line.lower()
        if any(p in h for p in patterns):
            out.append((i, line.rstrip("\n")))
    return out


def search_regex(lines, patterns, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = [re.compile(p, flags) for p in patterns]
    out = []
    for i, line in enumerate(lines, 1):
        if any(rx.search(line) for rx in compiled):
            out.append((i, line.rstrip("\n")))
    return out


# ---------- GUI ----------

class DumpSearcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("dump.cs Searcher")
        self.geometry("1100x700")
        self.minsize(800, 500)

        self.dump_path: Path | None = None
        self.lines = []
        self.results = []
        self.last_patterns = []

        self._build_ui()

    # ----- UI -----

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        # --- dump.cs ---
        row1 = ttk.Frame(top); row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="dump.cs:", width=10).pack(side=tk.LEFT)
        self.dump_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.dump_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="Обзор...", command=self.pick_dump).pack(side=tk.LEFT)

        # --- patterns ---
        row2 = ttk.Frame(top); row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Шаблоны:", width=10).pack(side=tk.LEFT)
        self.pattern_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.pattern_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row2, text="Из файла...", command=self.pick_patterns).pack(side=tk.LEFT)

        ttk.Label(top, text="Шаблоны можно разделять запятой или ; . "
                            "Например: Player, get_Health, Enemy",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 4))

        # --- options ---
        row3 = ttk.Frame(top); row3.pack(fill=tk.X, pady=2)

        self.regex_var = tk.BooleanVar(value=False)
        self.ignore_case_var = tk.BooleanVar(value=False)
        self.only_strings_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(row3, text="Regex", variable=self.regex_var).pack(side=tk.LEFT)
        ttk.Checkbutton(row3, text="Игнорировать регистр",
                        variable=self.ignore_case_var).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(row3, text="Только строковые литералы (\"...\")",
                        variable=self.only_strings_var).pack(side=tk.LEFT, padx=8)

        ttk.Label(row3, text="Контекст:").pack(side=tk.LEFT, padx=(16, 2))
        self.context_var = tk.IntVar(value=0)
        ttk.Spinbox(row3, from_=0, to=50, width=4,
                    textvariable=self.context_var).pack(side=tk.LEFT)

        # --- buttons ---
        row4 = ttk.Frame(top); row4.pack(fill=tk.X, pady=6)
        self.search_btn = ttk.Button(row4, text="🔍 Найти",
                                     command=self.run_search)
        self.search_btn.pack(side=tk.LEFT)
        ttk.Button(row4, text="📄 Сохранить в TXT",
                   command=self.save_results).pack(side=tk.LEFT, padx=6)
        ttk.Button(row4, text="📋 Копировать",
                   command=self.copy_results).pack(side=tk.LEFT)
        ttk.Button(row4, text="🧹 Очистить",
                   command=self.clear_results).pack(side=tk.LEFT, padx=6)

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(row4, textvariable=self.status_var,
                  foreground="blue").pack(side=tk.RIGHT)

        # --- output ---
        out_frame = ttk.LabelFrame(self, text="Результаты", padding=4)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.output = scrolledtext.ScrolledText(
            out_frame, wrap=tk.NONE, font=("Consolas", 10),
            background="#1e1e1e", foreground="#dcdcdc",
            insertbackground="white",
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        # теги для подсветки
        self.output.tag_configure("hit", foreground="#ff6b6b",
                                  font=("Consolas", 10, "bold"))
        self.output.tag_configure("lineno", foreground="#6a9955")
        self.output.tag_configure("sep", foreground="#444444")
        self.output.tag_configure("ctx", foreground="#9cdcfe")

        # автосохранение — путь по умолчанию
        self.autosave_var = tk.BooleanVar(value=True)
        row5 = ttk.Frame(top); row5.pack(fill=tk.X)
        ttk.Checkbutton(row5,
                        text="Автосохранять результаты в TXT рядом с dump.cs",
                        variable=self.autosave_var).pack(side=tk.LEFT)

    # ----- file pickers -----

    def pick_dump(self):
        path = filedialog.askopenfilename(
            title="Выбери dump.cs",
            filetypes=[("C# dump", "*.cs"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        self.dump_var.set(path)
        self._load_dump(Path(path))

    def pick_patterns(self):
        path = filedialog.askopenfilename(
            title="Файл с шаблонами",
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        pats = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        self.pattern_var.set(", ".join(pats))

    def _load_dump(self, path: Path):
        try:
            self.lines = read_file(path)
            self.dump_path = path
            self.status_var.set(f"Загружено строк: {len(self.lines)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
            self.lines = []
            self.dump_path = None

    # ----- search -----

    def _parse_patterns(self):
        raw = self.pattern_var.get().strip()
        if not raw:
            return []
        parts = re.split(r"[;,]", raw)
        return [p.strip() for p in parts if p.strip()]

    def run_search(self):
        if not self.dump_var.get():
            messagebox.showwarning("Внимание", "Сначала выбери dump.cs")
            return
        if not self.lines:
            self._load_dump(Path(self.dump_var.get()))
        if not self.lines:
            return

        patterns = self._parse_patterns()
        if not patterns:
            messagebox.showwarning("Внимание", "Введи хотя бы один шаблон")
            return

        # запуск в отдельном потоке, чтобы UI не фризился
        self.search_btn.config(state=tk.DISABLED)
        self.status_var.set("Поиск...")
        threading.Thread(
            target=self._search_worker,
            args=(patterns,),
            daemon=True,
        ).start()

    def _search_worker(self, patterns):
        case_sensitive = not self.ignore_case_var.get()
        try:
            if self.regex_var.get():
                results = search_regex(self.lines, patterns, case_sensitive)
            else:
                results = search_plain(self.lines, patterns, case_sensitive)
        except re.error as e:
            self.after(0, lambda: messagebox.showerror(
                "Ошибка regex", str(e)))
            self.after(0, lambda: self.search_btn.config(state=tk.NORMAL))
            return

        # фильтр "только строковые литералы"
        if self.only_strings_var.get():
            results = [(n, l) for n, l in results if '"' in l]

        self.after(0, self._render_results, results, patterns)

    def _render_results(self, results, patterns):
        self.results = results
        self.last_patterns = patterns

        self.output.delete("1.0", tk.END)
        ctx = self.context_var.get()
        case_sensitive = not self.ignore_case_var.get()

        if not results:
            self.output.insert(tk.END, "Ничего не найдено.\n")
            self.status_var.set("0 совпадений")
            self.search_btn.config(state=tk.NORMAL)
            return

        shown = set()
        for lineno, _ in results:
            start = max(1, lineno - ctx)
            end = min(len(self.lines), lineno + ctx)

            # пропускаем уже показанные (пересечения)
            if any(n in shown for n in range(start, end + 1)):
                pass

            for n in range(start, end + 1):
                if n in shown:
                    continue
                shown.add(n)
                text = self.lines[n - 1].rstrip("\n")
                self.output.insert(tk.END, f"{n:>7} | ", "lineno")
                if n == lineno:
                    self._insert_highlighted(text, patterns, case_sensitive)
                    self.output.insert(tk.END, "\n")
                else:
                    self.output.insert(tk.END, text + "\n", "ctx")
            self.output.insert(tk.END, "─" * 60 + "\n", "sep")

        self.status_var.set(f"Найдено: {len(results)}")
        self.search_btn.config(state=tk.NORMAL)

        # автосохранение
        if self.autosave_var.get() and self.dump_path:
            try:
                path = self._auto_save_path()
                self._write_txt(path)
                self.status_var.set(
                    f"Найдено: {len(results)}  →  сохранено: {path.name}")
            except Exception as e:
                print("autosave error:", e)

    def _insert_highlighted(self, line, patterns, case_sensitive):
        if not patterns:
            self.output.insert(tk.END, line)
            return
        flags = 0 if case_sensitive else re.IGNORECASE
        # собираем все совпадения
        spans = []
        for p in patterns:
            try:
                for m in re.finditer(re.escape(p), line, flags):
                    spans.append(m.span())
            except re.error:
                continue
        if not spans:
            self.output.insert(tk.END, line)
            return
        spans.sort()
        # объединяем пересечения
        merged = []
        for s, e in spans:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        pos = 0
        for s, e in merged:
            if s > pos:
                self.output.insert(tk.END, line[pos:s])
            self.output.insert(tk.END, line[s:e], "hit")
            pos = e
        if pos < len(line):
            self.output.insert(tk.END, line[pos:])

    # ----- saving -----

    def _auto_save_path(self) -> Path:
        if self.dump_path:
            return self.dump_path.with_name(
                self.dump_path.stem + "_search.txt")
        return Path("search_results.txt")

    def _write_txt(self, path: Path):
        ctx = self.context_var.get()
        case_sensitive = not self.ignore_case_var.get()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines_out = []
        lines_out.append("=" * 70)
        lines_out.append(f"dump.cs Search Results")
        lines_out.append(f"Дата:       {ts}")
        lines_out.append(f"Файл:       {self.dump_path}")
        lines_out.append(f"Шаблоны:    {', '.join(self.last_patterns)}")
        lines_out.append(f"Режим:      {'regex' if self.regex_var.get() else 'plain'}")
        lines_out.append(f"Регистр:    {'учитывается' if case_sensitive else 'игнорируется'}")
        lines_out.append(f"Контекст:   ±{ctx}")
        lines_out.append(f"Совпадений: {len(self.results)}")
        lines_out.append("=" * 70)
        lines_out.append("")

        shown = set()
        for lineno, _ in self.results:
            start = max(1, lineno - ctx)
            end = min(len(self.lines), lineno + ctx)
            for n in range(start, end + 1):
                if n in shown:
                    continue
                shown.add(n)
                text = self.lines[n - 1].rstrip("\n")
                marker = ">>" if n == lineno else "  "
                lines_out.append(f"{marker} {n:>7} | {text}")
            lines_out.append("-" * 70)

        path.write_text("\n".join(lines_out), encoding="utf-8")

    def save_results(self):
        if not self.results:
            messagebox.showinfo("Инфо", "Нечего сохранять — сначала найди что-нибудь.")
            return
        default = self._auto_save_path()
        path = filedialog.asksaveasfilename(
            title="Сохранить результаты",
            defaultextension=".txt",
            initialfile=default.name,
            initialdir=str(default.parent),
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            self._write_txt(Path(path))
            self.status_var.set(f"Сохранено: {Path(path).name}")
            messagebox.showinfo("Готово", f"Результаты сохранены:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

    def copy_results(self):
        if not self.results:
            return
        text = self.output.get("1.0", tk.END)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Скопировано в буфер")

    def clear_results(self):
        self.output.delete("1.0", tk.END)
        self.results = []
        self.status_var.set("Очищено")


if __name__ == "__main__":
    app = DumpSearcher()
    app.mainloop()