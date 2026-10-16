import doc_to_html as d


def test_int_to_roman():
    assert d.int_to_roman(4) == "IV"
    assert d.int_to_roman(14) == "XIV"
    assert d.int_to_roman(1994) == "MCMXCIV"


def test_resolve_list_marker_decimal():
    assert d.resolve_list_marker("%0.", 3) == "3."


def test_youtube_short_link_becomes_embed():
    url = d.generate_youtube_embed_url("https://youtu.be/dQw4w9WgXcQ")
    assert url == "https://www.youtube.com/embed/dQw4w9WgXcQ"


def test_update_styles_with_color_replaces_nested_placeholder_only():
    styles = {"a": "x {main_color} {keep}", "b": {"c": "{main_color}"}}
    d.update_styles_with_color(styles, "#123456")
    assert styles["a"] == "x #123456 {keep}"
    assert styles["b"]["c"] == "#123456"
