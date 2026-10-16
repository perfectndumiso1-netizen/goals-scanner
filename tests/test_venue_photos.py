"""Stadium photos must be free-licence, the right ground, and credited. No network in these tests."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

import venue_photos as vp


def page(title="File:Ground.jpg", lic="CC BY-SA 4.0", w=1920, h=1280, mime="image/jpeg", artist="<a href='x'>Jane Doe</a>", nonfree=None):
    meta = {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}}
    if nonfree:
        meta["NonFree"] = {"value": nonfree}
    return {"title": title, "imageinfo": [{"thumburl": "https://x/t.jpg", "url": "https://x/o.jpg", "width": w, "height": h,
                                           "mime": mime, "descriptionurl": "https://commons/File", "extmetadata": meta}]}


def test_only_free_licences_sensible_sizes_and_real_photos_pass():
    assert vp._candidate_from_page(page())["artist"] == "Jane Doe"                    # html stripped
    assert vp._candidate_from_page(page(lic="Public domain"))
    assert vp._candidate_from_page(page(lic="CC0"))
    assert vp._candidate_from_page(page(lic="All rights reserved")) is None
    assert vp._candidate_from_page(page(lic="CC BY-NC 4.0")) is None                  # commercial use needed
    assert vp._candidate_from_page(page(nonfree="1")) is None
    assert vp._candidate_from_page(page(w=800, h=600)) is None                         # too small
    assert vp._candidate_from_page(page(w=1500, h=2400)) is None                       # portrait
    assert vp._candidate_from_page(page(mime="image/svg+xml")) is None


def test_junk_titles_are_rejected_unless_it_is_the_curated_lead_image():
    for bad in ("File:Club logo.jpg", "File:Bugatti Circuit1.jpg", "File:Maquette de la MMArena.JPG", "File:Fans queue outside.jpg"):
        assert vp._candidate_from_page(page(title=bad)) is None
    assert vp._candidate_from_page(page(title="File:Stadium logo view.jpg"), lead=True) is not None


def test_noncommercial_and_noderivatives_licences_are_not_accepted():
    for bad in ("CC BY-NC-SA 4.0", "CC BY-NC 2.0", "CC BY-ND 4.0", "CC BY-NC-ND 3.0", "CC BY-ND", "All rights reserved", "Fair use", ""):
        assert not vp._is_free_license(bad), bad
    for good in ("CC BY-SA 3.0 de", "CC BY 2.5", "CC BY-SA 2.5 es", "CC BY-SA 4.0", "CC BY 4.0", "CC0", "CC0 1.0 Universal",
                 "Public domain", "Public domain (PD-US)"):
        assert vp._is_free_license(good), good


def test_credit_line_names_the_author_licence_and_source():
    c = vp._candidate_from_page(page(artist="Arne Müseler", lic="CC BY-SA 3.0 de"))
    assert vp.credit_line(c) == "Photo: Arne Müseler / CC BY-SA 3.0 de / Wikimedia Commons"


def test_display_names_are_presentable():
    assert vp.display_name("Waldstadion") == "Deutsche Bank Park"
    assert vp.display_name("stade Marie-Marvingt") == "Stade Marie-Marvingt"
    assert vp.display_name("Turf Moor") == "Turf Moor"


def test_club_resolves_to_its_current_ground_via_wikidata(monkeypatch):
    calls = []

    def fake(url, params):
        calls.append(params.get("action"))
        if params["action"] == "wbsearchentities":
            return {"search": [{"id": "Q1", "description": "women's association football club"},
                               {"id": "Q2", "description": "association football club in France"}]}
        if params["action"] == "wbgetentities" and params["ids"] == "Q2":
            return {"entities": {"Q2": {"claims": {"P115": [
                {"mainsnak": {"datavalue": {"value": {"id": "Q9"}}}, "qualifiers": {"P582": [1]}},      # former ground
                {"mainsnak": {"datavalue": {"value": {"id": "Q8"}}}}]}}}}
        if params["action"] == "wbgetentities" and params["ids"] == "Q8":
            return {"entities": {"Q8": {"labels": {"en": {"value": "stade Marie-Marvingt"}},
                                        "claims": {"P373": [{"mainsnak": {"datavalue": {"value": "Stade Marie-Marvingt"}}}]}}}}
        return {}

    monkeypatch.setattr(vp, "_get_json", fake)
    info = vp.venue_info("Le Mans")
    assert info["name"] == "stade Marie-Marvingt" and info["category"] == "Stade Marie-Marvingt" and info["qid"] == "Q8"


def test_archival_black_and_white_scans_are_skipped(tmp_path: Path):
    grey, colour = tmp_path / "g.jpg", tmp_path / "c.jpg"
    Image.new("RGB", (200, 120), (120, 120, 120)).save(grey)
    Image.new("RGB", (200, 120), (30, 140, 60)).save(colour)
    assert vp._is_monochrome(grey) and not vp._is_monochrome(colour)


def test_no_ground_found_means_no_photos_not_a_wrong_one(monkeypatch, tmp_path):
    monkeypatch.setattr(vp, "venue_info", lambda team: None)
    assert vp.venue_photos("Nobody FC", tmp_path) == []
