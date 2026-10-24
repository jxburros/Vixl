"""Brand kit deliverables: a logo delivery package, a brand guidelines board, device, print and merch mockups and
print-ready art."""

PLUGIN = {
    "name": "brand_kit",
    "title": "Brand kit",
    "summary": "Logo packages, brand guideline boards, device, print and merch mockups and print-ready art from a "
               "brand.json and a logo.",
    "kind": "workflows",
    "modules": ["logo_package", "brand_board", "mockups", "drawing", "garments", "goods", "accessories", "products", "finishes", "print_art",
                "workflow"],
    "workflows": ["workflow"],
    "requires": ["drawing", "workspace_qa"],
}
