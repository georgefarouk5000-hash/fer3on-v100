__all__ = ["Fer3onMasrApp"]


def __getattr__(name):
    if name == "Fer3onMasrApp":
        from .app import Fer3onMasrApp
        return Fer3onMasrApp
    raise AttributeError(name)
