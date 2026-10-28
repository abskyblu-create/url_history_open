import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
from html.parser import HTMLParser

STATES = ('Unreviewed', 'Keep', 'Skip', 'Later', 'Opened')
PROVIDERS = {
    'Online courses': ['coursera.org', 'udemy.com', 'edx.org', 'udacity.com', 'skillshare.com', 'pluralsight.com', 'khanacademy.org', 'datacamp.com', 'futurelearn.com'],
    'Videos': ['youtube.com', 'youtu.be', 'vimeo.com'],
    'Developer resources': ['github.com', 'gitlab.com', 'stackoverflow.com', 'readthedocs.io', 'developer.mozilla.org'],
    'Research': ['arxiv.org', 'scholar.google.com', 'pubmed.ncbi.nlm.nih.gov', 'doi.org'],
    'Articles and blogs': ['medium.com', 'substack.com', 'dev.to'],
}


def classify(url):
    host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
    for category, domains in PROVIDERS.items():
        if any(host == domain or host.endswith('.' + domain) for domain in domains):
            return host, category
    if host == 'linkedin.com' and urlsplit(url).path.startswith('/learning'):
        return host, 'Online courses'
    return host, 'Other'


def make_item(url):
    site, category = classify(url)
    hint = re.sub(r'[-_]+', ' ', unquote(urlsplit(url).path).strip('/')).replace('/', ' / ')
    return dict(url=url, site=site, category=specific_category(url), title=hint or site,
                description='URL-based hint only. Fetch page information for its title and description.',
                status='Unreviewed', preview='Not fetched')


SUBJECTS = [
    ('Generative AI and LLMs', r'\b(llms?|chatgpt|generative ai|prompt engineering|langchain|rag)\b'),
    ('Deep learning', r'\b(deep learning|neural networks?|pytorch|tensorflow)\b'),
    ('Machine learning', r'\b(machine learning|scikit learn|reinforcement learning)\b'),
    ('Data science and analytics', r'\b(data science|data analysis|data analytics|pandas|numpy|power bi|tableau)\b'),
    ('Databases and SQL', r'\b(sql|mysql|postgresql|mongodb|databases?)\b'),
    ('Python', r'\bpython\b'),
    ('JavaScript and web development', r'\b(javascript|typescript|react|angular|vue|html|css|web development|nextjs|nodejs)\b'),
    ('Java', r'\bjava\b'),
    ('Cloud and DevOps', r'\b(aws|azure|gcp|cloud|docker|kubernetes|devops|terraform)\b'),
    ('Cybersecurity', r'\b(cybersecurity|cyber security|ethical hacking|penetration testing|network security)\b'),
    ('Mathematics and statistics', r'\b(mathematics|calculus|algebra|statistics|probability)\b'),
    ('Business and finance', r'\b(business|finance|accounting|investing|entrepreneurship)\b'),
    ('Marketing', r'\b(marketing|seo|advertising)\b'),
    ('Design and UX', r'\b(design|ux|figma|photoshop)\b'),
    ('Languages', r'\b(english|french|german|spanish|language learning)\b'),
]


def specific_category(url, title='', description=''):
    """Suggest hierarchy from explicit URL/metadata terms, without guessing content."""
    host, broad = classify(url)
    path = unquote(urlsplit(url).path).lower()
    text = re.sub(r'[^\w]+', ' ', ' '.join((path, title.lower(), description.lower())))
    subject = next((label for label, pattern in SUBJECTS if re.search(pattern, text)), None)
    kind = None
    if broad == 'Online courses':
        if '/professional-certificates/' in path:
            kind = 'Professional certificates'
        elif '/specializations/' in path:
            kind = 'Specializations'
        elif '/degrees/' in path:
            kind = 'Degrees'
        elif any(part in path for part in ('/learn/', '/course/', '/courses/')):
            kind = 'Courses'
        elif any(part in path for part in ('/search', '/browse', '/catalog')):
            kind = 'Catalog and search'
        else:
            kind = 'General'
    elif broad == 'Videos':
        kind = 'Playlists' if '/playlist' in path else 'Channels' if any(p in path for p in ('/@', '/channel/', '/c/')) else 'Short videos' if '/shorts/' in path else 'Videos'
    elif host in ('github.com', 'gitlab.com'):
        kind = 'Issues' if '/issues' in path else 'Pull requests' if '/pull/' in path or '/merge_requests' in path else 'Repositories' if len(path.strip('/').split('/')) >= 2 else 'Profiles and discovery'
    elif broad == 'Developer resources':
        kind = 'Questions and answers' if host == 'stackoverflow.com' else 'Documentation'
    elif broad == 'Research':
        kind = 'Papers and publications'
    elif broad == 'Articles and blogs':
        kind = 'Articles'
    if broad == 'Other':
        return ' / '.join([subject or 'Other websites', host])
    return ' / '.join(part for part in (broad, subject or 'Subject not identified', kind) if part)


class PageInfo(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = ''
        self.description = ''
        self.text = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.ignored += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'meta' and (attrs.get('name', '').lower() == 'description' or attrs.get('property', '').lower() == 'og:description'):
            self.description = self.description or attrs.get('content', '')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.ignored = max(0, self.ignored - 1)
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if not self.ignored:
            self.text.append(data)


def fetch_preview(url, include_content=False):
    request = Request(url, headers={'User-Agent': 'URLReview/1.0', 'Accept': 'text/html'})
    with urlopen(request, timeout=10) as response:
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Not an HTML page; no description available.')
        raw = response.read(512 * 1024)
        encoding = response.headers.get_content_charset() or 'utf-8'
        try:
            html = raw.decode(encoding, errors='replace')
        except LookupError:
            html = raw.decode('utf-8', errors='replace')
    parser = PageInfo()
    parser.feed(html)
    preview = (' '.join(parser.title.split())[:500], ' '.join(parser.description.split())[:2000])
    if include_content:
        return (*preview, ' '.join(' '.join(parser.text).split())[:12000])
    return preview


class Review:
    def __init__(self, filename, urls, directory='.reviews'):
        self.source_path = Path(filename).resolve()
        self.path = Path(directory) / (hashlib.sha256(str(Path(filename).resolve()).encode()).hexdigest() + '.json')
        saved = {}
        self.warning = ''
        if self.path.exists():
            try:
                saved = {item['url']: item for item in json.loads(self.path.read_text(encoding='utf-8')) if isinstance(item, dict) and 'url' in item}
            except (OSError, ValueError, TypeError):
                self.warning = 'Saved review could not be read; starting a new review.'
        self.items = []
        for url in urls:
            item = make_item(url)
            previous = saved.get(url, {})
            item['deleted'] = previous.get('deleted') is True
            for key in ('title', 'description', 'category', 'preview', 'status', 'page_text'):
                if isinstance(previous.get(key), str):
                    item[key] = previous[key]
            # Upgrade old automatic categories while retaining manually assigned topics.
            legacy_auto = previous.get('category') in (*PROVIDERS, 'Other')
            item['custom_category'] = previous.get('custom_category', bool(previous.get('category')) and not legacy_auto)
            if not item['custom_category']:
                item['category'] = specific_category(url, item['title'], item['description'] if item['preview'] != 'Not fetched' else '')
            if item['status'] not in STATES:
                item['status'] = 'Unreviewed'
            self.items.append(item)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
