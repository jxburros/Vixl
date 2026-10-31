"""Vector animation interchange and explicit animated raster fallbacks."""

PLUGIN = {
    'name': 'lottie',
    'title': 'Lottie animation',
    'summary': 'Export vector animations with native easing and time-remapped linked instances as Lottie JSON, dotLottie and strict Telegram TGS.',
    'kind': 'workflows',
    'modules': ['lottie'],
    'hooks': {'timeline-export-format': ['lottie:export']},
}
