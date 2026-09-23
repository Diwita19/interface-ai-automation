from html import escape


STYLES = """
:root {
    color-scheme: light;
    --background: #f3f6fb;
    --surface: #ffffff;
    --text: #17243b;
    --muted: #607089;
    --border: #dce4ef;
    --primary: #2257c7;
    --primary-hover: #19449e;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--background);
    color: var(--text);
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 16px;
    line-height: 1.6;
}

.site-header {
    background: #14294b;
    color: #ffffff;
    border-bottom: 4px solid #719cf3;
}

.header-content,
.page-container,
.site-footer {
    width: min(100% - 40px, 960px);
    margin-inline: auto;
}

.header-content {
    padding-block: 30px;
}

.brand-label {
    margin: 0 0 6px;
    color: #b6caf0;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

h1 {
    margin: 0;
    font-size: clamp(25px, 4vw, 34px);
    line-height: 1.25;
    letter-spacing: -0.03em;
}

.site-description {
    margin: 10px 0 0;
    color: #d0dcf0;
    font-size: 14px;
}

.page-container {
    padding-block: 36px;
}

.content-card {
    overflow-wrap: anywhere;
    padding: clamp(22px, 4vw, 40px);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 12px 34px rgba(20, 41, 75, 0.06);
}

h2 {
    margin: 0 0 22px;
    font-size: clamp(23px, 3vw, 28px);
    line-height: 1.3;
    letter-spacing: -0.025em;
}

h3 {
    margin: 30px 0 14px;
    font-size: 18px;
}

p {
    margin: 14px 0;
}

.content-card > p {
    color: var(--muted);
}

form {
    max-width: 540px;
}

label {
    display: block;
    margin-bottom: 9px;
    font-size: 14px;
    font-weight: 600;
}

input[type="text"] {
    display: block;
    width: 100%;
    min-height: 48px;
    margin-bottom: 18px;
    padding: 11px 14px;
    background: #ffffff;
    color: var(--text);
    border: 1px solid #b8c6d9;
    border-radius: 9px;
    font: inherit;
}

button {
    min-height: 46px;
    padding: 11px 22px;
    background: var(--primary);
    color: #ffffff;
    border: 1px solid var(--primary);
    border-radius: 9px;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
}

button:hover {
    background: var(--primary-hover);
    border-color: var(--primary-hover);
}

a {
    color: var(--primary);
    text-decoration-thickness: 1px;
    text-underline-offset: 3px;
}

a:hover {
    color: var(--primary-hover);
}

.content-card > p > a {
    display: inline-block;
    padding: 8px 13px;
    background: #f0f5ff;
    border: 1px solid #d7e3fb;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
}

.content-card > p > a:hover {
    background: #e4edff;
}

a:focus-visible,
button:focus-visible,
input:focus-visible {
    outline: 3px solid #d58b12;
    outline-offset: 4px;
}

table {
    width: 100%;
    margin: 20px 0;
    border-spacing: 0;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}

th,
td {
    padding: 15px 18px;
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid var(--border);
    overflow-wrap: anywhere;
}

th {
    background: #f5f8fd;
    color: #465773;
    font-size: 14px;
    font-weight: 600;
}

td {
    font-variant-numeric: tabular-nums;
}

tbody th[scope="row"] {
    width: 38%;
}

tbody tr:last-child > th,
tbody tr:last-child > td {
    border-bottom: none;
}

.review-note {
    margin-bottom: 24px;
    padding: 16px 18px;
    background: #fff8e8;
    color: #765214;
    border: 1px solid #efd8a7;
    border-radius: 10px;
}

.review-note p {
    margin: 0;
}

.review-note p + p {
    margin-top: 8px;
}

.review-check {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin: 20px 0;
    padding: 16px;
    background: #f5f8fd;
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
}

input[type="checkbox"] {
    flex: 0 0 auto;
    width: 19px;
    height: 19px;
    margin: 3px 0 0;
    accent-color: var(--primary);
}

.site-footer {
    padding-bottom: 28px;
    color: var(--muted);
    font-size: 12px;
}

@media (max-width: 560px) {
    .header-content,
    .page-container,
    .site-footer {
        width: min(100% - 24px, 960px);
    }

    .header-content {
        padding-block: 24px;
    }

    .page-container {
        padding-block: 20px;
    }

    th,
    td {
        padding: 12px 10px;
    }

    button {
        width: 100%;
    }
}
"""


def render_page(title: str, body: str) -> str:
    """Render trusted page markup inside the shared application layout."""

    safe_title = escape(title)

    # Callers must escape dynamic values inserted into body.
    # CSS is embedded so the browser needs no extra asset requests.
    return f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta
                name="viewport"
                content="width=device-width, initial-scale=1"
            >
            <title>{safe_title} | Demo Credit Union</title>
            <style>{STYLES}</style>
        </head>
        <body>
            <header class="site-header">
                <div class="header-content">
                    <p class="brand-label">Member services</p>
                    <h1>Demo Credit Union</h1>
                    <p class="site-description">
                        Synthetic training application. No real customer data.
                    </p>
                </div>
            </header>

            <main class="page-container">
                <section class="content-card">
                    {body}
                </section>
            </main>

            <footer class="site-footer">
                Local demonstration &middot; Synthetic accounts only
            </footer>
        </body>
    </html>
    """