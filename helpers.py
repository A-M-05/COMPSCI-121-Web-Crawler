from imports import *

# ---------------- THREAD-SAFE ANALYTICS ----------------

_ANALYTICS_LOCK = threading.Lock()

UNIQUE_PAGES = set()
LONGEST_PAGE_URL = None
LONGEST_PAGE_WORDS = 0
WORD_FREQ = Counter()
SUBDOMAIN_PAGES = defaultdict(set)

PATH_QUERY_SEEN = defaultdict(set)


# ---------------- UTILS ----------------

def to_text(content):
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return str(content)


def extract_visible_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript","header","footer","nav","aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def tokenize(text):
    return WORD_RE.findall(text.lower())


def host_allowed(host):
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


# ---------------- URL HANDLING ----------------

def normalize_url(url):
    s = urlsplit(url)
    scheme = s.scheme.lower()
    netloc = s.netloc.lower()

    path = s.path.rstrip("/") if s.path != "/" else "/"

    params = []
    for k, v in parse_qsl(s.query, keep_blank_values=False):
        if k.lower() not in TRAP_QUERY_KEYS:
            params.append((k.lower(), v))

    params.sort()
    params = params[:MAX_PARAMS]

    query = urlencode(params, doseq=True)
    if len(query) > MAX_QUERY_LEN:
        query = ""

    return urlunsplit((scheme, netloc, path, query, ""))


def canonicalize_for_count(url):
    clean, _ = urldefrag(url)
    s = urlsplit(clean)
    scheme = s.scheme.lower()
    netloc = s.netloc.lower()
    path = s.path.rstrip("/") if s.path != "/" else "/"
    return urlunsplit((scheme, netloc, path, s.query, ""))


# ---------------- TRAP DETECTION ----------------

def has_trap_query(parsed):
    return any(k.lower() in TRAP_QUERY_KEYS for k,_ in parse_qsl(parsed.query))


def has_trap_path(path):
    p = path.lower()
    return any(t in p for t in TRAP_PATH_SUBSTRINGS)


def too_many_variants(url):
    s = urlsplit(url)
    key = (s.netloc.lower(), s.path.lower())
    if not s.query:
        return False
    PATH_QUERY_SEEN[key].add(s.query)
    return len(PATH_QUERY_SEEN[key]) > MAX_VARIANTS_PER_PATH


# ---------------- ANALYTICS ----------------

def update_analytics(url, text):
    global LONGEST_PAGE_URL, LONGEST_PAGE_WORDS

    canon = canonicalize_for_count(url)
    parsed = urlparse(canon)
    host = parsed.hostname or ""

    tokens = tokenize(text)
    word_count = len(tokens)

    with _ANALYTICS_LOCK:
        if canon in UNIQUE_PAGES:
            return

        UNIQUE_PAGES.add(canon)

        if word_count > LONGEST_PAGE_WORDS:
            LONGEST_PAGE_WORDS = word_count
            LONGEST_PAGE_URL = canon

        for t in tokens:
            if t not in STOP_WORDS:
                WORD_FREQ[t] += 1

        if host.endswith(".uci.edu") and host != "uci.edu":
            SUBDOMAIN_PAGES[host].add(canon)


def dump_analytics():
    with open("crawl_analytics.txt", "w") as f:
        f.write(f"Unique pages: {len(UNIQUE_PAGES)}\n")
        f.write(f"Longest page ({LONGEST_PAGE_WORDS} words):\n{LONGEST_PAGE_URL}\n\n")

        f.write("Top 50 words:\n")
        for w,c in WORD_FREQ.most_common(50):
            f.write(f"{w}, {c}\n")

        f.write("\nSubdomains:\n")
        for sd in sorted(SUBDOMAIN_PAGES):
            f.write(f"{sd}, {len(SUBDOMAIN_PAGES[sd])}\n")


atexit.register(dump_analytics)