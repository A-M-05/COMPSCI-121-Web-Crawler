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
    # Only record non-empty URLs
    if url:
        # Add to the global set of bad URLs
        BAD_URLS.add(url)

def is_bad_url(url: str) -> bool:
    """
    Return True if URL was previously recorded as bad.
    URL should already be normalized/defragmented by caller.
    """
    # Membership test in BAD_URLS set
    return url in BAD_URLS


# ---------------- UTILS ----------------

def to_text(content):
    """
    Convert raw response content into a Python string.
    Handles None, bytes, and already-string-like content.
    """
    # If content is missing, return empty string
    if content is None:
        return ""
    # If content is bytes, decode as UTF-8 (ignore bad byte sequences)
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    # Otherwise, coerce to string
    return str(content)


def extract_visible_text(html):
    """
    Extract visible human-readable text from HTML by removing
    common non-content tags (scripts, nav, etc.) and returning the text.
    """
    # Parse HTML into a BeautifulSoup DOM
    soup = BeautifulSoup(html, "html.parser")
    # Remove tags that usually contain non-visible or repeated boilerplate content
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        # Delete the entire tag subtree from the DOM
        tag.decompose()
    # Return visible text, separated by spaces, trimmed of extra whitespace
    return soup.get_text(separator=" ", strip=True)


def tokenize(text_content: str) -> list[str]:
    """
    Returns tokens EXCLUDING stopwords and digits.
    Used for 'top words' (content words).
    """
    # Build the current token one character at a time
    current = []
    # Store finalized tokens here
    all_tokens = []

    # Normalize to lowercase for consistent token comparison
    text_lower = text_content.lower()

    # Scan the text character-by-character
    for char in text_lower:
        # Keep ASCII alphanumeric chars as part of the current token
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            # If we hit a delimiter and we have a token buffered, flush it
            if current:
                token = ''.join(current)
                # Keep token only if non-empty, not a stopword, and not pure digits
                if token and token not in STOP_WORDS and not token.isdigit():
                    all_tokens.append(token)
                # Reset buffer for next token
                current = []

    # Flush final buffered token if text ended mid-token
    if current:
        token = ''.join(current)
        # Apply same filtering rules as above
        if token and token not in STOP_WORDS and not token.isdigit():
            all_tokens.append(token)

    # Return list of filtered content tokens
    return all_tokens


def tokenize_with_stopwords(text_content: str) -> list[str]:
    """
    Returns tokens INCLUDING stopwords (excluding pure digits).
    Used to compute stopword frequencies.
    """
    # Buffer for the token currently being built
    current = []
    # Collected tokens (includes stopwords)
    tokens = []

    # Normalize to lowercase so counts are case-insensitive
    text_lower = text_content.lower()

    # Scan the text character-by-character
    for char in text_lower:
        # Keep ASCII alphanumeric chars in the current token
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            # On delimiter, flush buffered token if it exists
            if current:
                token = ''.join(current)
                # Keep token only if non-empty and not pure digits
                if token and not token.isdigit():
                    tokens.append(token)
                # Reset buffer for next token
                current = []

    # Flush final buffered token if text ended mid-token
    if current:
        token = ''.join(current)
        # Apply same filtering rules as above
        if token and not token.isdigit():
            tokens.append(token)

    # Return list of tokens including stopwords
    return tokens

def host_allowed(host: str) -> bool:
    """
    Return True if host matches or is a subdomain of one of ALLOWED_DOMAINS.
    """
    # Accept exact match or any subdomain that ends with ".<allowed_domain>"
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


# ---------------- URL HANDLING ----------------

def normalize_url(url: str) -> str:
    """
    Strips fragments, lowercases scheme+host, trims trailing slash, drops trap query keys,
    sorts remaining query params, caps count/length.
    """
    # Remove fragment (#...) part so same page with different fragments collapses
    clean, _ = urldefrag(url)
    # Split URL into (scheme, netloc, path, query, fragment)
    s = urlsplit(clean)

    # Normalize scheme and host casing
    scheme = (s.scheme or "").lower()
    netloc = (s.netloc or "").lower()

    # remove default ports
    if netloc.endswith(":80") and scheme == "http":
        # Drop :80 for http URLs
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        # Drop :443 for https URLs
        netloc = netloc[:-4]

    # Normalize path: remove trailing slash except keep "/" as root
    path = s.path.rstrip("/") if s.path and s.path != "/" else "/"

    # Collect safe query params (dropping trap keys)
    params = []
    for k, v in parse_qsl(s.query, keep_blank_values=False):
        # Lowercase key for consistent filtering/deduping
        lk = k.lower()
        # Keep only non-trap query keys
        if lk not in TRAP_QUERY_KEYS:
            params.append((lk, v))

    # Sort params for canonical ordering (a=1&b=2 == b=2&a=1)
    params.sort()
    # Cap number of query params to avoid query explosion
    params = params[:MAX_PARAMS]

    # Re-encode query string
    query = urlencode(params, doseq=True)
    # If query is too long, drop it entirely to avoid trap variants
    if len(query) > MAX_QUERY_LEN:
        query = ""

    # Return fully normalized URL without fragment
    return urlunsplit((scheme, netloc, path, query, ""))


def canonicalize_for_count(url: str) -> str:
    """
    Canonical form for UNIQUE_PAGES: uses normalize_url so we don't treat
    trivial query order / tracking params as different pages.
    """
    try:
        # Preferred canonicalization strategy: reuse normalize_url
        return normalize_url(url)
    except Exception:
        # Fallback: do best-effort canonicalization without the full normalize_url logic
        clean, _ = urldefrag(url)
        s = urlsplit(clean)
        scheme = s.scheme.lower()
        netloc = s.netloc.lower()
        path = s.path.rstrip("/") if s.path != "/" else "/"
        return urlunsplit((scheme, netloc, path, s.query, ""))


# ---------------- TRAP DETECTION ----------------

def has_trap_query(parsed) -> bool:
    """
    Return True if any query key is in TRAP_QUERY_KEYS.
    """
    # Parse query into (key, value) pairs and check keys against TRAP_QUERY_KEYS
    return any(k.lower() in TRAP_QUERY_KEYS for k, _ in parse_qsl(parsed.query))


def has_trap_path(path: str) -> bool:
    """
    Return True if the path contains any known trap substrings.
    """
    # Normalize path to lowercase; handle None safely
    p = (path or "").lower()
    # If any trap substring appears in the path, treat as trap
    return any(t in p for t in TRAP_PATH_SUBSTRINGS)


def too_many_variants(url: str) -> bool:
    """
    Limits pages that keep producing new queries for same path.
    Must be thread-safe.
    """
    # Split URL so we can access netloc/path/query
    s = urlsplit(url)
    # If there is no query string, variant control doesn't apply
    if not s.query:
        return False

    # Use (host, path) as the bucket key
    key = (s.netloc.lower(), s.path.lower())
    # Protect shared PATH_QUERY_SEEN structure across threads
    with _VARIANTS_LOCK:
        # Record this specific query string for that (host, path)
        PATH_QUERY_SEEN[key].add(s.query)
        # If we've seen too many distinct queries for that path, treat as trap
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

    # Canonicalize URL for counting unique pages
    canon = canonicalize_for_count(url)
    # Parse canonical URL to extract host information
    parsed = urlparse(canon)
    # Normalize host to lowercase; avoid None
    host = parsed.hostname.lower() or ""

    # For subdomain reporting, treat www.* as the same subdomain
    if host.startswith("www."):
        host = host[4:]

    # Tokens excluding stopwords (for "top content words")
    content_tokens = tokenize(text)
    # Tokens including stopwords (for longest page + stopword frequency)
    all_tokens = tokenize_with_stopwords(text)
    # Word count is token count including stopwords (excluding pure digits)
    word_count = len(all_tokens)

    # Lock analytics so updates are thread-safe and UNIQUE_PAGES behaves correctly
    with _ANALYTICS_LOCK:
        # If we already counted this canonical URL, don't double-count or re-add frequencies
        if canon in UNIQUE_PAGES:
            return

        # Record this page as unique
        UNIQUE_PAGES.add(canon)

        # Update longest page tracking if this page is bigger
        if word_count > LONGEST_PAGE_WORDS:
            LONGEST_PAGE_WORDS = word_count
            LONGEST_PAGE_URL = canon

        # content words
        for t in content_tokens:
            # Ignore very short tokens and domain-noise words
            if len(t) >= 2 and t not in DOMAIN_STOP_WORDS:
                # Increment frequency for content word reporting
                WORD_FREQ[t] += 1

        # stopwords
        for t in all_tokens:
            # Only count if token is in STOP_WORDS list
            if t in STOP_WORDS:
                # Increment stopword frequency
                STOPWORD_FREQ[t] += 1

        # uci.edu subdomains
        if host.endswith(".uci.edu") and host != "uci.edu":
            # Track which unique pages were found under each subdomain
            SUBDOMAIN_PAGES[host].add(canon)


def dump_analytics():
    """
    Write crawl analytics summary to crawl_analytics.txt at program exit.
    """
    # Open output file for writing (overwrites prior run)
    with open("crawl_analytics.txt", "w") as f:
        # Write unique page count
        f.write(f"Unique pages: {len(UNIQUE_PAGES)}\n")
        # Write longest page info
        f.write(f"Longest page ({LONGEST_PAGE_WORDS} words):\n{LONGEST_PAGE_URL}\n\n")

        # Write most common content words (non-stopwords)
        f.write("Top 50 content words (non-stopwords):\n")
        for w, c in WORD_FREQ.most_common(50):
            f.write(f"{w}, {c}\n")

        # Write most common stopwords
        f.write("\nTop 50 stopwords:\n")
        for w, c in STOPWORD_FREQ.most_common(50):
            f.write(f"{w}, {c}\n")

        # Write subdomain list and page counts per subdomain
        f.write("\nSubdomains under uci.edu:\n")
        for sd in sorted(SUBDOMAIN_PAGES):
            f.write(f"{sd}, {len(SUBDOMAIN_PAGES[sd])}\n")


# Register analytics dump so it runs automatically when the process exits normally
atexit.register(dump_analytics)