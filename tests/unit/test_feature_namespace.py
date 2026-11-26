from components.matter.data_model.clusters import CLUSTERS, CLUSTERS_BY_CONF_KEY

# A feature namespace is emitted directly as C++ (esp_matter::cluster::<cluster>::
# feature::<namespace>), so it must be a valid identifier. A namespace that is a
# reserved word does not compile; see issue #91 for the FanControl `auto` feature.
CPP_KEYWORDS = frozenset(
    {
        "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
        "bool", "break", "case", "catch", "char", "class", "compl", "const",
        "constexpr", "continue", "decltype", "default", "delete", "do", "double",
        "dynamic_cast", "else", "enum", "explicit", "export", "extern", "false",
        "float", "for", "friend", "goto", "if", "inline", "int", "long", "mutable",
        "namespace", "new", "noexcept", "not", "not_eq", "nullptr", "operator",
        "or", "or_eq", "private", "protected", "public", "register",
        "reinterpret_cast", "return", "short", "signed", "sizeof", "static",
        "static_assert", "static_cast", "struct", "switch", "template", "this",
        "thread_local", "throw", "true", "try", "typedef", "typeid", "typename",
        "union", "unsigned", "using", "virtual", "void", "volatile", "wchar_t",
        "while", "xor", "xor_eq",
    }
)


def test_fan_control_auto_uses_fan_auto_namespace() -> None:
    """esp-matter names the FanControl Auto feature `fan_auto`; `auto` is a C++ keyword (#91)."""
    cluster = CLUSTERS_BY_CONF_KEY["fan_control"]
    auto = next(feature for feature in cluster.features if feature.name == "Auto")
    assert auto.namespace == "fan_auto"


def test_no_feature_namespace_is_a_cpp_keyword() -> None:
    """A feature namespace that is a reserved word generates uncompilable C++ (#91)."""
    offenders = [
        f"{cluster.conf_key}.{feature.name} -> {feature.namespace}"
        for cluster in CLUSTERS
        for feature in cluster.features
        if feature.namespace in CPP_KEYWORDS
    ]
    assert not offenders, (
        "Feature namespaces that are C++ keywords (add an override in "
        "_ESP_MATTER_FEATURE_NAMESPACES): " + ", ".join(offenders)
    )
