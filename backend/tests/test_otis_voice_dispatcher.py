from agents.otis_voice_dispatcher import _extract_origin_dest, _fmt_transport


def test_extract_origin_dest_handles_standard_route_phrase():
    origin, dest = _extract_origin_dest("Show me trains from Mumbai to Pune today")

    assert origin == "Mumbai"
    assert dest == "Pune"


def test_extract_origin_dest_handles_missing_to_between_cities():
    origin, dest = _extract_origin_dest("Give me train plans for today from Toronto Mumbai")

    assert origin == "Toronto"
    assert dest == "Mumbai"


def test_format_transport_highlights_train_platforms_for_voice():
    text = _fmt_transport(
        {
            "recommended_mode": "train",
            "modes": {
                "train": {
                    "available": True,
                    "estimated_duration": "3.2 hrs",
                    "popular_trains": ["Deccan Express (12123)"],
                    "platforms": [{"name": "IRCTC"}],
                }
            },
        },
        "Mumbai",
        "Pune",
    )

    assert "Deccan Express" in text
    assert "IRCTC" in text
    assert "3.2 hrs" in text
