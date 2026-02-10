from imports import *

# ---------------- THREAD-SAFE ANALYTICS ----------------

_ANALYTICS_LOCK = threading.Lock()
_VARIANTS_LOCK = threading.Lock()

UNIQUE_PAGES = set()                 # canonical URL strings
LONGEST_PAGE_URL = None
LONGEST_PAGE_WORDS = 0

WORD_FREQ = Counter()                # non-stopword tokens
STOPWORD_FREQ = Counter()            # stopword tokens (what you asked for)
SUBDOMAIN_PAGES = defaultdict(set)   # host -> set(canonical urls)

PATH_QUERY_SEEN = defaultdict(set)   # (netloc, path) -> set(queries)


BAD_URLS = set()

def mark_bad_url(url: str) -> None:
    """
    Record a URL as "bad" so we can refuse it later.
    URL should already be normalized/defragmented by caller.
    """
    if url:
        BAD_URLS.add(url)

def is_bad_url(url: str) -> bool:
    """
    Return True if URL was previously recorded as bad.
    URL should already be normalized/defragmented by caller.
    """
    return url in BAD_URLS


# ---------------- UTILS ----------------

def to_text(content):
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return str(content)


def extract_visible_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def tokenize(text_content: str) -> list[str]:
    """
    Returns tokens EXCLUDING stopwords and digits.
    Used for 'top words' (content words).
    """
    current = []
    all_tokens = []

    text_lower = text_content.lower()

    for char in text_lower:
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            if current:
                token = ''.join(current)
                if token and token not in STOP_WORDS and not token.isdigit():
                    all_tokens.append(token)
                current = []

    if current:
        token = ''.join(current)
        if token and token not in STOP_WORDS and not token.isdigit():
            all_tokens.append(token)

    return all_tokens


def tokenize_with_stopwords(text_content: str) -> list[str]:
    """
    Returns tokens INCLUDING stopwords (excluding pure digits).
    Used to compute stopword frequencies.
    """
    current = []
    tokens = []

    text_lower = text_content.lower()

    for char in text_lower:
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            if current:
                token = ''.join(current)
                if token and not token.isdigit():
                    tokens.append(token)
                current = []

    if current:
        token = ''.join(current)
        if token and not token.isdigit():
            tokens.append(token)

    return tokens


def count_all_words(text_content: str) -> int:
    """
    Count ALL words including stopwords (for longest page calculation).
    """
    current = []
    count = 0

    text_lower = text_content.lower()

    for char in text_lower:
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            if current:
                count += 1
                current = []
    if current:
        count += 1
    return count


def host_allowed(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


# ---------------- URL HANDLING ----------------

def normalize_url(url: str) -> str:
    """
    Strips fragments, lowercases scheme+host, trims trailing slash, drops trap query keys,
    sorts remaining query params, caps count/length.
    """
    clean, _ = urldefrag(url)
    s = urlsplit(clean)

    scheme = (s.scheme or "").lower()
    netloc = (s.netloc or "").lower()

    # remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = s.path.rstrip("/") if s.path and s.path != "/" else "/"

    params = []
    for k, v in parse_qsl(s.query, keep_blank_values=False):
        lk = k.lower()
        if lk not in TRAP_QUERY_KEYS:
            params.append((lk, v))

    params.sort()
    params = params[:MAX_PARAMS]

    query = urlencode(params, doseq=True)
    if len(query) > MAX_QUERY_LEN:
        query = ""

    return urlunsplit((scheme, netloc, path, query, ""))


def canonicalize_for_count(url: str) -> str:
    """
    Canonical form for UNIQUE_PAGES: uses normalize_url so we don't treat
    trivial query order / tracking params as different pages.
    """
    try:
        return normalize_url(url)
    except Exception:
        clean, _ = urldefrag(url)
        s = urlsplit(clean)
        scheme = s.scheme.lower()
        netloc = s.netloc.lower()
        path = s.path.rstrip("/") if s.path != "/" else "/"
        return urlunsplit((scheme, netloc, path, s.query, ""))


# ---------------- TRAP DETECTION ----------------

def has_trap_query(parsed) -> bool:
    return any(k.lower() in TRAP_QUERY_KEYS for k, _ in parse_qsl(parsed.query))


def has_trap_path(path: str) -> bool:
    p = (path or "").lower()
    return any(t in p for t in TRAP_PATH_SUBSTRINGS)


def too_many_variants(url: str) -> bool:
    """
    Limits pages that keep producing new queries for same path.
    Must be thread-safe.
    """
    s = urlsplit(url)
    if not s.query:
        return False

    key = (s.netloc.lower(), s.path.lower())
    with _VARIANTS_LOCK:
        PATH_QUERY_SEEN[key].add(s.query)
        return len(PATH_QUERY_SEEN[key]) > MAX_VARIANTS_PER_PATH


# ---------------- ANALYTICS ----------------

def update_analytics(url: str, text: str):
    """
    Updates:
      1) UNIQUE_PAGES count
      2) longest page by word count
      3) top content words (non-stopwords)
      4) top stopwords
      5) subdomain counts under uci.edu
    """
    global LONGEST_PAGE_URL, LONGEST_PAGE_WORDS

    canon = canonicalize_for_count(url)
    parsed = urlparse(canon)
    host = parsed.hostname or ""

    word_count = count_all_words(text)
    content_tokens = tokenize(text)
    all_tokens = tokenize_with_stopwords(text)

    with _ANALYTICS_LOCK:
        if canon in UNIQUE_PAGES:
            return

        UNIQUE_PAGES.add(canon)

        if word_count > LONGEST_PAGE_WORDS:
            LONGEST_PAGE_WORDS = word_count
            LONGEST_PAGE_URL = canon

        # content words
        for t in content_tokens:
            if len(t) >= 2 and t not in DOMAIN_STOP_WORDS:
                WORD_FREQ[t] += 1

        # stopwords
        for t in all_tokens:
            if t in STOP_WORDS:
                STOPWORD_FREQ[t] += 1

        # uci.edu subdomains
        if host.endswith(".uci.edu") and host != "uci.edu":
            SUBDOMAIN_PAGES[host].add(canon)


def dump_analytics():
    with open("crawl_analytics.txt", "w") as f:
        f.write(f"Unique pages: {len(UNIQUE_PAGES)}\n")
        f.write(f"Longest page ({LONGEST_PAGE_WORDS} words):\n{LONGEST_PAGE_URL}\n\n")

        f.write("Top 50 content words (non-stopwords):\n")
        for w, c in WORD_FREQ.most_common(50):
            f.write(f"{w}, {c}\n")

        f.write("\nTop 50 stopwords:\n")
        for w, c in STOPWORD_FREQ.most_common(50):
            f.write(f"{w}, {c}\n")

        f.write("\nSubdomains under uci.edu:\n")
        for sd in sorted(SUBDOMAIN_PAGES):
            f.write(f"{sd}, {len(SUBDOMAIN_PAGES[sd])}\n")


atexit.register(dump_analytics)