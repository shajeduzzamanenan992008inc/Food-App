from flask import current_app, g, request, session


SUPPORTED_LOCALES = {
    "en_US": "English (US)",
    "bn_BD": "বাংলা",
    "hi_IN": "हिन्दी",
    "ar": "العربية",
}


def get_request_locale():
    """Resolve a supported locale from account, explicit session, browser, then default."""
    user = getattr(g, "current_user", None)
    if user and user.preferred_locale in SUPPORTED_LOCALES:
        return user.preferred_locale

    selected = session.get("locale")
    if selected in SUPPORTED_LOCALES:
        return selected

    locale_aliases = {
        "en": "en_US",
        "en-us": "en_US",
        "bn": "bn_BD",
        "bn-bd": "bn_BD",
        "hi": "hi_IN",
        "hi-in": "hi_IN",
        "ar": "ar",
    }
    for language, _quality in request.accept_languages:
        normalized = language.replace("_", "-").lower()
        if normalized in locale_aliases:
            return locale_aliases[normalized]
        base_language = normalized.split("-", 1)[0]
        if base_language in locale_aliases:
            return locale_aliases[base_language]

    return current_app.config.get("BABEL_DEFAULT_LOCALE", "en_US")
