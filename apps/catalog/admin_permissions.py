"""Права на операции, затрагивающие сразу несколько моделей каталога."""
IMPORT_PERMISSIONS = (
    "catalog.add_motorcycle", "catalog.change_motorcycle",
    "catalog.add_variant", "catalog.change_variant", "catalog.delete_variant",
    "catalog.add_motorcycleoption", "catalog.change_motorcycleoption", "catalog.delete_motorcycleoption",
    "catalog.view_optiondef",
)
EXPORT_PERMISSIONS = ("catalog.view_motorcycle", "catalog.view_variant", "catalog.view_motorcycleoption",
                      "catalog.view_optiondef")
DUPLICATE_PERMISSIONS = (*EXPORT_PERMISSIONS, "catalog.add_motorcycle", "catalog.add_variant",
                         "catalog.add_motorcycleoption")
