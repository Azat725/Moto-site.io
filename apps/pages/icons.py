"""SVG-иконки и концепты логотипа (только палитра сайта: красный, белый, чёрный)."""

ICONS = {
    "pin": '<path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "bolt": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    "battery": '<rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 11v2M6 10v4M10 10v4"/>',
    "speed": '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-6"/>',
    "route": '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"/>',
    "truck": '<path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.6 0-1.2-1-1.6-1-2.6 0-.9.7-1.6 1.6-1.6H17a4 4 0 0 0 4-4c0-4.6-4-8.2-9-8.2z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7" r="1"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "sliders": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "chat": '<path d="M4 5h16v11H8l-4 4z"/>',
    "tools": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2.5-.6-.6-2.5z"/>',
}

# Три концепта «дерзкого» логотипа. Выбор по умолчанию — SITE_LOGO в настройках.
LOGOS = {
    # Молния, разрезающая щит; верхние концы молнии — «рога»
    "volt": (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M8 6l10 8h28l10-8-2 16-6 26-16 12-16-12-6-26z" fill="#E10600"/>'
        '<path d="M36 12L20 36h10l-4 18 18-26H34l6-16z" fill="#fff"/>'
        '<path d="M8 6l10 8M56 6l-10 8" stroke="#0B0B0C" stroke-width="3" stroke-linecap="round"/></svg>'
    ),
    # Рогатый угловатый щит с ядром-молнией
    "horns": (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M4 2c4 10 8 14 16 16h24c8-2 12-6 16-16-1 12-4 18-8 22l-4 22-16 14-16-14-4-22C8 20 5 14 4 2z" fill="#0B0B0C" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/>'
        '<path d="M12 22h40l-4 22-16 12-16-12z" fill="#E10600"/>'
        '<path d="M34 24l-10 16h7l-3 12 12-17h-7l4-11z" fill="#fff"/></svg>'
    ),
    # Агрессивная курсивная буква V с «клыком» и искрой
    "fang": (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="64" height="64" rx="14" fill="#0B0B0C"/>'
        '<path d="M10 12h14l8 26 14-26h10L34 54h-8l-4-12-6 6z" fill="#E10600"/>'
        '<path d="M46 12l-6 12h6l-8 14" stroke="#fff" stroke-width="3" fill="none" stroke-linejoin="round"/></svg>'
    ),
}
