"""AI providers: image generation, editing and vision through configured model providers and gateways."""

PLUGIN = {
    "name": "ai",
    "title": "AI providers",
    "summary": "Generate, edit, detect and describe images through configured providers; model discovery and routing.",
    "kind": "provider",
    "modules": ["ai", "models", "studio_provider", "command_provider"],
    "hooks": {"host-flags": ["studio_provider:host_flags"], "host-route": ["studio_provider:host_routes"]},
    "requires": ["drawing"],
}
