from bs4 import BeautifulSoup


def html_to_text_bs4(html: str | None) -> str | None:
    if html is None:
        return None

    if html == "":
        return ""

    soup = BeautifulSoup(html, "lxml")  # or "html.parser"
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text()
    # normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
