def navigation_context(request):
    """Provide navigation context variables to all templates."""
    resolver_match = getattr(request, 'resolver_match', None)
    if not resolver_match:
        return {'current_module': '', 'current_view': '', 'module_display_name': 'AEGIS'}

    namespace = resolver_match.namespace or ''
    url_name = resolver_match.url_name or ''

    MODULE_NAMES = {
        'asp_alerts': 'ASP Alerts',
        'hai_detection': 'HAI Detection',
        'mdro': 'MDRO Surveillance',
        'drug_bug': 'Drug-Bug Mismatch',
        'dosing': 'Dosing Verification',
        'outbreak_detection': 'Outbreak Detection',
        'antimicrobial_usage': 'Antimicrobial Usage',
        'abx_indications': 'ABX Indications',
        'surgical_prophylaxis': 'Surgical Prophylaxis',
        'guideline_adherence': 'Guideline Adherence',
        'nhsn_reporting': 'NHSN Reporting',
        'action_analytics': 'Action Analytics',
    }

    return {
        'current_module': namespace,
        'current_view': url_name,
        'module_display_name': MODULE_NAMES.get(namespace, 'AEGIS'),
    }
