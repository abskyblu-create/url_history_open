"""Review spreadsheet links before opening selected batches in Edge."""
import csv
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from collections import Counter
from urllib.parse import unquote

from review import Review, STATES, fetch_preview, specific_category
from urls import read_urls
from source_edit import delete_from_source


def find_edge():
    executable = shutil.which('msedge')
    if executable:
        return executable
    for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / 'Microsoft/Edge/Application/msedge.exe'
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError('Microsoft Edge was not found.')


class App:
    def __init__(self, root):
        self.root = root
        self.review = None
        self.results = queue.Queue()
        self.busy = False
        self.semantic_busy = False
        self.semantic_matches = None
        self.semantic_results = queue.Queue()
        self.semantic_engine = None
        self.search_version = 0
        root.title('Smart URL Review - Microsoft Edge')
        root.geometry('1180x820')
        root.minsize(960, 700)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Review first. Open only what you want.', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        top = ttk.Frame(frame)
        top.pack(fill='x', pady=10)
        ttk.Button(top, text='Choose CSV / Excel', command=self.load).pack(side='left')
        ttk.Button(top, text='Export review CSV', command=self.export).pack(side='left', padx=8)
        self.summary = tk.StringVar(value='Choose a file. Nothing opens automatically.')
        ttk.Label(frame, textvariable=self.summary).pack(anchor='w', pady=6)
        filters = ttk.Frame(frame)
        filters.pack(fill='x', pady=6)
        self.filters = {}
        for key, label, width in [('category', 'Topic', 48), ('site', 'Website', 24), ('status', 'Decision', 15)]:
            ttk.Label(filters, text=label).pack(side='left', padx=(0, 4))
            variable = tk.StringVar(value='All')
            combo = ttk.Combobox(filters, textvariable=variable, values=['All'], state='readonly', width=width)
            combo.pack(side='left', padx=(0, 10))
            combo.bind('<<ComboboxSelected>>', lambda event: self.refresh())
            self.filters[key] = (variable, combo)
        self.search = tk.StringVar()
        search_row = ttk.Frame(frame)
        search_row.pack(fill='x', pady=4)
        ttk.Label(search_row, text='Search:').pack(side='left', padx=(0, 6))
        self.search_entry = ttk.Entry(search_row, textvariable=self.search)
        self.search_entry.pack(side='left', fill='x', expand=True)
        self.search_entry.bind('<Return>', self.perform_search)
        ttk.Button(search_row, text='Search', command=self.perform_search).pack(side='left', padx=6)
        self.semantic_button = ttk.Button(search_row, text='Semantic search', command=self.perform_semantic_search)
        self.semantic_button.pack(side='left', padx=(0, 6))
        ttk.Button(search_row, text='Clear', command=self.clear_search).pack(side='left')
        ttk.Label(frame, text='Search/Enter: words. Semantic search: related ideas, best 50 matches. Fetch page info for better coverage.').pack(anchor='w')
        self.search.trace_add('write', self.search_changed)
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True, pady=8)
        self.table = ttk.Treeview(table_frame, columns=('status', 'category', 'site', 'title'), show='headings', selectmode='extended')
        for name, width in [('status', 95), ('category', 340), ('site', 180), ('title', 330)]:
            self.table.heading(name, text=name.title())
            self.table.column(name, width=width, minwidth=70)
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', self.show_detail)
        self.table.bind('<Control-a>', self.select_all)
        self.link_menu = tk.Menu(root, tearoff=False)
        self.link_menu.add_command(label='Open this link in Edge', command=self.open_selected)
        self.link_menu.add_command(label='Delete link', command=self.delete_selected)
        self.table.bind('<Button-3>', self.show_link_menu)
        self.detail = tk.Text(frame, height=7, wrap='word', font=('Segoe UI', 10), state='disabled')
        self.detail.pack(fill='x')
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=8)
        for state in ('Keep', 'Skip', 'Later', 'Unreviewed'):
            ttk.Button(actions, text=state, command=lambda value=state: self.decide(value)).pack(side='left', padx=(0, 6))
        self.fetch = ttk.Button(actions, text='Fetch selected page info (max 20)', command=self.fetch_selected)
        self.fetch.pack(side='left', padx=8)
        ttk.Button(actions, text='Fetch next 20 unread pages', command=self.fetch_unread).pack(side='left')
        group = ttk.Frame(frame)
        group.pack(fill='x', pady=4)
        ttk.Label(group, text='Move selected to topic:').pack(side='left')
        self.custom_category = tk.StringVar()
        ttk.Entry(group, textvariable=self.custom_category, width=30).pack(side='left', padx=6)
        ttk.Button(group, text='Apply topic', command=self.assign_category).pack(side='left')
        opening = ttk.Frame(frame)
        opening.pack(fill='x', pady=8)
        ttk.Label(opening, text='Tabs per window:').pack(side='left')
        self.batch_size = tk.StringVar(value='20')
        ttk.Spinbox(opening, from_=1, to=20, textvariable=self.batch_size, width=4).pack(side='left', padx=6)
        ttk.Button(opening, text='Open next kept batch in current filters', command=self.open_kept).pack(side='left', padx=6)
        ttk.Button(opening, text='Open one selected link to inspect', command=self.open_selected).pack(side='left')
        self.notice = tk.StringVar(value='Topic suggestions use website rules. Page descriptions are fetched only when requested.')
        ttk.Label(frame, textvariable=self.notice, wraplength=1100).pack(anchor='w')
        root.after(150, self.poll)

    def select_all(self, event=None):
        self.table.selection_set(self.table.get_children())
        return 'break'

    def perform_search(self, event=None):
        self.semantic_matches = None
        self.search_version += 1
        for variable, _ in self.filters.values():
            variable.set('All')
        self.refresh()
        if self.review:
            query = self.search.get().strip()
            self.notice.set(f'{len(self.visible())} matching link(s) across all groups' + (f' for "{query}".' if query else '.'))
        return 'break'

    def search_changed(self, *_):
        self.semantic_matches = None
        self.search_version += 1
        self.refresh()

    def perform_semantic_search(self):
        if not self.review or self.semantic_busy:
            return
        query = self.search.get().strip()
        if not query:
            messagebox.showinfo('Enter a search', 'Describe what you need, for example beginner programming lessons or renewable energy research.')
            return
        self.semantic_busy = True
        self.semantic_button.configure(state='disabled')
        self.semantic_matches = None
        self.search_version += 1
        version = self.search_version
        snapshot = [dict(item) for item in self.review.items]
        self.notice.set('Searching locally with Gemma and Ollama. Keep Ollama running.')
        def worker():
            try:
                if self.semantic_engine is None:
                    from semantic import SemanticSearch
                    self.semantic_engine = SemanticSearch()
                matches = self.semantic_engine.search(snapshot, query, lambda text: self.semantic_results.put(('progress', version, text)))
                self.semantic_results.put(('done', version, matches))
            except Exception as exc:
                self.semantic_results.put(('error', version, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def clear_search(self):
        self.search.set('')
        self.refresh()
        self.search_entry.focus_set()

    def delete_selected(self):
        selected = self.selected()
        if not self.review or len(selected) != 1:
            return
        try:
            changed, backup = delete_from_source(self.review.source_path, self.review.items[selected[0]]['url'])
        except Exception as exc:
            messagebox.showerror('Link not deleted', str(exc))
            return
        self.review.items[selected[0]]['deleted'] = True
        self.save()
        self.refresh()
        self.notice.set(f'Link removed from {changed} source cell(s) and this review. Backup: {backup.name}')

    def show_link_menu(self, event):
        row = self.table.identify_row(event.y)
        if not row:
            return
        # The menu always targets the clicked row, even after a multi-selection.
        self.table.selection_set(row)
        self.table.focus(row)
        self.show_detail()
        try:
            self.link_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.link_menu.grab_release()

    def selected(self):
        return [int(i) for i in self.table.selection()]

    def visible(self):
        if not self.review:
            return []
        terms = self.search.get().casefold().split()
        visible = [i for i, item in enumerate(self.review.items)
                if not item.get('deleted')
                and all(variable.get() in ('All', item[key]) for key, (variable, _) in self.filters.items())
                and ((i in self.semantic_matches) if self.semantic_matches is not None else all(term in ' '.join(unquote(item[key]) for key in ('url', 'title', 'description', 'site', 'category')).casefold() for term in terms))]
        if self.semantic_matches is not None:
            visible.sort(key=lambda i: self.semantic_matches[i], reverse=True)
        return visible

    def refresh(self):
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        if not self.review:
            return
        for key, (variable, combo) in self.filters.items():
            options = ['All'] + (list(STATES) if key == 'status' else sorted({item[key] for item in self.review.items if not item.get('deleted')}))
            combo['values'] = options
            if variable.get() not in options:
                variable.set('All')
        visible = self.visible()
        for i in visible:
            item = self.review.items[i]
            self.table.insert('', 'end', iid=str(i), values=[item[key] for key in ('status', 'category', 'site', 'title')])
        surviving = [i for i in selected if self.table.exists(i)]
        if surviving:
            self.table.selection_set(surviving)
        elif visible:
            self.table.selection_set(str(visible[0]))
        active = [item for item in self.review.items if not item.get('deleted')]
        counts = Counter(item['status'] for item in active)
        self.summary.set(f'{len(active)} links | {len(visible)} shown | ' + ' | '.join(f'{state}: {counts[state]}' for state in STATES))
        self.show_detail()

    def show_detail(self, event=None):
        selected = self.selected()
        text = ''
        if self.review and selected:
            item = self.review.items[selected[0]]
            text = f"{item['title']}\n{item['url']}\nTopic: {item['category']} | Website: {item['site']} | Decision: {item['status']}\n{item['description']}\nPreview: {item['preview']}"
            if self.semantic_matches is not None and selected[0] in self.semantic_matches:
                text += f"\nSemantic similarity: {self.semantic_matches[selected[0]]:.3f} (ranking score, not a probability). Search interpreted by local Gemma."
                text += '\nSearch basis: ' + ('fetched page text and metadata' if item.get('page_text') else 'URL and available metadata only; fetch page info to improve coverage')
            if len(selected) > 1:
                text += f'\n{len(selected)} links selected; decisions apply to all selected links.'
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('1.0', text)
        self.detail.configure(state='disabled')

    def save(self):
        try:
            self.review.save()
        except OSError as exc:
            messagebox.showerror('Review not saved', str(exc))

    def load(self):
        if self.busy or self.semantic_busy:
            messagebox.showinfo('Work in progress', 'Wait for preview requests or semantic search to finish.')
            return
        filename = filedialog.askopenfilename(filetypes=[('CSV or Excel', '*.csv *.xlsx *.xls')])
        if not filename:
            return
        try:
            review = Review(filename, read_urls(filename))
        except Exception as exc:
            messagebox.showerror('Could not read file', str(exc))
            return
        self.review = review
        for variable, _ in self.filters.values():
            variable.set('All')
        self.search.set('')
        self.refresh()
        self.notice.set(review.warning or 'Keep, Skip and Later decisions are saved locally as you work.')

    def decide(self, state):
        selected = self.selected()
        if not selected:
            return
        order = self.visible()
        following = next((i for i in order if i > max(selected) and self.review.items[i]['status'] == 'Unreviewed'), None)
        for i in selected:
            self.review.items[i]['status'] = state
        self.save()
        self.refresh()
        if len(selected) == 1 and following is not None and self.table.exists(str(following)):
            self.table.selection_set(str(following))
            self.table.see(str(following))

    def assign_category(self):
        category = self.custom_category.get().strip()
        if not category or not self.selected():
            return
        for i in self.selected():
            self.review.items[i]['category'] = category
            self.review.items[i]['custom_category'] = True
        self.save()
        self.refresh()

    def fetch_unread(self):
        if not self.review or self.busy:
            return
        indices = [i for i, item in enumerate(self.review.items) if not item.get('deleted') and not item.get('page_text') and not item.get('preview', '').startswith('Unavailable:')][:20]
        if not indices:
            messagebox.showinfo('Page information', 'No unread pages remain. Failed pages can be selected and fetched again manually.')
            return
        self.fetch_selected(indices)

    def fetch_selected(self, indices=None):
        selected = self.selected() if indices is None else indices
        if self.busy or not selected:
            return
        if len(selected) > 20:
            messagebox.showinfo('Choose fewer links', 'Select up to 20 links at a time for page previews.')
            return
        self.busy = True
        self.fetch.configure(state='disabled')
        self.notice.set('Fetching page titles and descriptions. No tabs are opened.')
        requests = [(i, self.review.items[i]['url']) for i in selected]
        def worker():
            for i, url in requests:
                try:
                    title, description, content = fetch_preview(url, include_content=True)
                    self.results.put((i, title, description, None, content))
                except Exception as exc:
                    self.results.put((i, '', '', str(exc)))
            self.results.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        changed = False
        while True:
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                break
            if result is None:
                self.busy = False
                self.fetch.configure(state='normal')
                self.notice.set('Previews finished. Login-only or blocked pages may not provide information.')
                continue
            i, title, description, error = result[:4]
            item = self.review.items[i]
            if error:
                item['preview'] = 'Unavailable: ' + error
            else:
                item['title'] = title or item['title']
                item['description'] = description or 'The page did not supply a description.'
                item['preview'] = 'Website-provided text, not an AI summary.'
                if len(result) > 4:
                    item['page_text'] = result[4]
                if not item.get('custom_category'):
                    item['category'] = specific_category(item['url'], item['title'], item['description'])
            changed = True
        if changed:
            self.semantic_matches = None
            self.search_version += 1
            self.save()
            self.refresh()
        while True:
            try:
                kind, version, payload = self.semantic_results.get_nowait()
            except queue.Empty:
                break
            if kind != 'progress':
                self.semantic_busy = False
                self.semantic_button.configure(state='normal')
            if version != self.search_version:
                continue
            if kind == 'progress':
                self.notice.set(payload)
            elif kind == 'error':
                self.notice.set('Semantic search failed; word search remains available.')
                messagebox.showerror('Semantic search unavailable', payload + '\nStart Ollama. Required local models: gemma3:4b and qwen3-embedding:0.6b.')
            else:
                self.semantic_matches = payload
                for variable, _ in self.filters.values():
                    variable.set('All')
                self.refresh()
                missing = sum(not item.get('page_text') for item in self.review.items if not item.get('deleted'))
                self.notice.set(f'{len(payload)} semantic matches (best 50, similarity >= 0.30). {missing} links have no fetched page text; fetch page info then rerun for better coverage. Edit the query for word search.')
        self.root.after(150, self.poll)

    def launch(self, indices, mark_opened=True):
        try:
            subprocess.Popen([find_edge(), '--new-window', *[self.review.items[i]['url'] for i in indices]])
        except (OSError, ValueError) as exc:
            messagebox.showerror('Could not open Edge', str(exc))
            return
        if mark_opened:
            for i in indices:
                self.review.items[i]['status'] = 'Opened'
            self.save()
            self.refresh()
        self.notice.set(f'Launched {len(indices)} link(s) in one Edge window. Review more when ready.')

    def open_kept(self):
        try:
            size = int(self.batch_size.get())
            if not 1 <= size <= 20:
                raise ValueError
        except ValueError:
            messagebox.showerror('Invalid batch size', 'Choose 1 to 20 tabs per window.')
            return
        indices = [i for i in self.visible() if self.review.items[i]['status'] == 'Keep'][:size]
        if not indices:
            messagebox.showinfo('No kept links', 'Mark links Keep first. Check your filters if kept links are hidden.')
            return
        self.launch(indices)

    def open_selected(self):
        indices = self.selected()
        if len(indices) != 1:
            messagebox.showinfo('Select one link', 'Select exactly one link to inspect in Edge.')
            return
        self.launch(indices, mark_opened=False)

    def export(self):
        if not self.review:
            return
        filename = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='url-review.csv', filetypes=[('CSV', '*.csv')])
        if not filename:
            return
        try:
            with open(filename, 'w', encoding='utf-8-sig', newline='') as stream:
                fields = ['url', 'site', 'category', 'status', 'title', 'description', 'preview']
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for item in self.review.items:
                    if item.get('deleted'):
                        continue
                    writer.writerow({key: "'" + item[key] if item[key].startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else item[key] for key in fields})
            self.notice.set('All links and decisions exported to ' + filename)
        except OSError as exc:
            messagebox.showerror('Export failed', str(exc))


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
