CLAN_MAP_COLOR_GROUPS = (
    {"key": "red", "colors": ("#D32F2F",)},
    {"key": "orange", "colors": ("#E64A19", "#F57C00")},
    {"key": "yellow", "colors": ("#FFB300", "#FBC02D")},
    {"key": "green", "colors": ("#C0CA33", "#7CB342", "#43A047", "#2E7D32", "#9E9D24")},
    {"key": "cyan", "colors": ("#00897B", "#00ACC1")},
    {"key": "blue", "colors": ("#039BE5", "#1E88E5", "#3949AB")},
    {"key": "purple", "colors": ("#5E35B1", "#8E24AA")},
    {"key": "pink", "colors": ("#D81B60", "#C2185B", "#AD1457")},
    {"key": "earth", "colors": ("#6D4C41", "#8D6E63")},
    {"key": "neutral", "colors": ("#546E7A", "#455A64")},
)

CLAN_MAP_COLORS = {
    color
    for group in CLAN_MAP_COLOR_GROUPS
    for color in group["colors"]
}
