from __future__ import annotations

from pathlib import Path

# A [hopefully] comprehensive list of all file extensions that we should consider plaintext or text-based.
# This is the source of truth for determining whether a file's text content should be indexed or not.
# Examples of files that should NOT be indexed: images, videos, etc
PLAINTEXT_EXTENSIONS = {
    # Scripts
    ".bash",  # Bash scripts
    ".bats",  # Bash Automated Testing System
    ".sh",  # Shell scripts
    ".ps1",  # PowerShell scripts
    ".psm1",  # PowerShell modules
    ".psd1",  # PowerShell data files
    ".awk",  # AWK scripting
    ".tcl",  # TCL scripting
    ".ahk",  # AutoHotkey scripts
    # Programming languages
    ".c",  # C source
    ".cc",  # C++ source
    ".cpp",  # C++ source
    ".cxx",  # C++ source
    ".c++",  # C++ source
    ".h",  # C/C++ header
    ".hh",  # C++ header
    ".hpp",  # C++ header
    ".cs",  # C#
    ".java",  # Java
    ".php",  # PHP
    ".rb",  # Ruby
    ".rs",  # Rust
    ".swift",  # Swift
    ".kt",  # Kotlin
    ".kts",  # Kotlin script
    ".scala",  # Scala
    ".clj",  # Clojure
    ".cljs",  # ClojureScript
    ".edn",  # Extensible Data Notation
    ".dart",  # Dart
    ".elm",  # Elm
    ".fs",  # F#
    ".fsx",  # F# script
    ".fsi",  # F# signature
    ".ml",  # OCaml
    ".mli",  # OCaml interface
    ".hs",  # Haskell
    ".lhs",  # Literate Haskell
    ".erl",  # Erlang
    ".hrl",  # Erlang header
    ".ex",  # Elixir
    ".exs",  # Elixir script
    ".jl",  # Julia
    ".nim",  # Nim
    ".cr",  # Crystal
    ".d",  # D
    ".v",  # V language / Verilog
    ".vhd",  # VHDL hardware description
    ".vhdl",  # VHDL hardware description
    ".zig",  # Zig language
    ".odin",  # Odin language
    ".groovy",  # Groovy scripts
    ".gleam",  # Gleam language
    ".roc",  # Roc language
    ".purs",  # PureScript
    ".dhall",  # Dhall configuration language
    ".pas",  # Pascal
    ".pp",  # Pascal
    ".pl",  # Perl
    ".pm",  # Perl module
    ".t",  # Perl test
    ".r",  # R
    ".R",  # R
    ".m",  # Objective-C/MATLAB
    ".mm",  # Objective-C++
    ".vb",  # Visual Basic
    ".vbs",  # VBScript
    ".asm",  # Assembly
    ".s",  # Assembly
    ".S",  # Assembly
    ".nasm",  # NASM Assembly
    ".masm",  # MASM Assembly
    ".f",  # Fortran
    ".f90",  # Fortran 90
    ".f95",  # Fortran 95
    ".for",  # Fortran
    ".ftn",  # Fortran
    ".cob",  # COBOL
    ".cbl",  # COBOL
    ".cobol",  # COBOL
    ".ada",  # Ada
    ".adb",  # Ada body
    ".ads",  # Ada specification
    ".go",  # Go source
    ".js",  # JavaScript
    ".cjs",  # CommonJS JavaScript
    ".jsx",  # React JSX
    ".mjs",  # ES6 modules JavaScript
    ".ts",  # TypeScript
    ".tsx",  # TypeScript JSX
    ".cts",  # CommonJS TypeScript
    ".mts",  # ES6 modules TypeScript
    ".d.ts",  # TypeScript declaration files
    ".d.mts",  # ES module TypeScript declarations
    ".d.cts",  # CommonJS TypeScript declarations
    ".py",  # Python
    ".lua",  # Lua scripts
    ".coffee",  # CoffeeScript
    ".vim",  # Vim script
    ".lisp",  # Common Lisp
    ".scm",  # Scheme
    ".rkt",  # Racket
    ".el",  # Emacs Lisp
    ".sol",  # Solidity (blockchain)
    ".vy",  # Vyper (blockchain)
    ".wat",  # WebAssembly Text
    ".as",  # ActionScript
    ".hx",  # Haxe
    ".hack",  # Hack language
    # Web/Markup
    ".html",  # HTML
    ".htm",  # HTML (short)
    ".xhtml",  # XHTML
    ".xml",  # XML
    ".xsd",  # XML Schema Definition
    ".dtd",  # Document Type Definition
    ".xsl",  # XSL stylesheets
    ".xslt",  # XSLT stylesheets
    ".rss",  # RSS feeds
    ".atom",  # Atom feeds
    ".soap",  # SOAP XML
    ".wsdl",  # Web Services Description Language
    ".css",  # CSS styles
    ".scss",  # Sass CSS
    ".sass",  # Sass CSS (indented syntax)
    ".less",  # Less CSS
    ".styl",  # Stylus CSS
    ".stylus",  # Stylus CSS
    ".ejs",  # Embedded JavaScript templates
    ".vue",  # Vue.js components
    ".svelte",  # Svelte components
    ".astro",  # Astro components
    ".blade",  # Laravel Blade templates
    ".twig",  # Twig templates
    ".mustache",  # Mustache templates
    ".hbs",  # Handlebars templates
    ".handlebars",  # Handlebars templates
    ".erb",  # Embedded Ruby templates
    ".haml",  # Haml templates
    ".slim",  # Slim templates
    ".pug",  # Pug templates (formerly Jade)
    ".jade",  # Jade templates (legacy)
    ".j2",  # Jinja2 templates
    ".jinja",  # Jinja templates
    ".jinja2",  # Jinja2 templates
    ".liquid",  # Liquid templates (Shopify)
    ".njk",  # Nunjucks templates
    ".marko",  # Marko templates
    ".xaml",  # XAML (WPF/UWP/Avalonia)
    ".svg",  # SVG graphics
    ".webmanifest",  # Web app manifest
    # Data/Config
    ".json",  # JSON data
    ".json5",  # JSON5 (JSON with comments and trailing commas)
    ".hjson",  # Human JSON
    ".cson",  # CoffeeScript Object Notation
    ".csv",  # Comma-separated values
    ".yaml",  # YAML data
    ".yml",  # YAML data (short)
    ".conf",  # Configuration files
    ".plist",  # Property list (macOS)
    ".ron",  # Rusty Object Notation
    ".kdl",  # KDL configuration language
    ".neon",  # NEON configuration
    ".dotenv",  # Environment files
    ".flaskenv",  # Flask environment
    ".ipynb",  # Jupyter notebooks
    # Documentation
    ".md",  # Markdown
    ".mdc",  # Markdown with components
    ".mdx",  # Markdown with JSX
    ".markdown",  # Markdown variant
    ".mdown",  # Markdown variant
    ".litcoffee",  # Literate CoffeeScript
    ".txt",  # Plain text
    ".man",  # Manual pages
    ".texi",  # Texinfo
    ".texinfo",  # Texinfo
    # Database/Query
    ".sql",  # SQL queries
    ".prisma",  # Prisma schema
    # Infrastructure/DevOps
    ".tf",  # Terraform
    ".tfvars",  # Terraform variables
    ".tfstate",  # Terraform state
    ".hcl",  # HashiCorp Configuration Language
    ".tftpl",  # Terraform templates
    ".pkr.hcl",  # Packer configuration
    ".nomad",  # Nomad job files
    ".rego",  # Open Policy Agent rules
    ".sentinel",  # Sentinel policy files
    ".jenkinsfile",  # Jenkins pipeline files
    ".jsonnet",  # Jsonnet configuration
    ".tilt",  # Tiltfile (Kubernetes dev)
    # Templates
    ".template",  # Generic templates
    ".tmpl",  # Go templates
    # Patches
    ".patch",  # Git patches
    ".diff",  # Diff files
    # Scripts
    ".zsh",
    ".fish",
    ".csh",
    ".tcsh",
    ".ksh",
    ".bat",
    ".cmd",
    ".nu",  # Nushell scripts
    ".elvish",  # Elvish shell
    # Config files
    ".ini",
    ".cfg",
    ".config",
    ".properties",
    ".toml",
    ".lock",
    ".env",
    ".envrc",
    ".rc",  # Generic RC files
    ".profile",  # Shell profile
    ".bash_profile",  # Bash profile
    ".nix",  # Nix configuration
    ".just",  # Justfiles (command runner)
    ".direnv",  # direnv configuration
    ".nvmrc",  # NVM configuration
    ".ruby-version",  # Ruby version
    ".python-version",  # Python version
    ".node-version",  # Node version
    ".tool-versions",  # asdf tool versions
    # Build files
    ".gradle",
    ".gradle.kts",  # Kotlin Gradle scripts
    ".maven",
    ".ant",
    ".make",
    ".mk",  # Makefile variant
    ".am",  # Automake files
    ".ac",  # Autoconf files
    ".cmake",
    ".ninja",  # Ninja build system
    ".bazel",
    ".bzl",
    ".BUILD",
    ".WORKSPACE",
    ".gyp",  # Generate Your Projects
    ".gypi",  # GYP include
    ".gn",  # GN build system
    ".gni",  # GN include
    ".sbt",  # Scala Build Tool
    ".cabal",  # Haskell Cabal
    ".opam",  # OCaml OPAM
    # Documentation
    ".rst",
    ".adoc",
    ".asciidoc",
    ".textile",
    ".org",  # Org-mode files
    ".tex",  # LaTeX documents
    ".bib",  # BibTeX bibliography
    ".pod",  # Perl POD documentation
    ".rdoc",  # Ruby documentation
    ".qmd",  # Quarto markdown
    ".rmd",  # R Markdown
    ".feature",  # Cucumber/Gherkin BDD tests
    ".spec",  # Specification files
    # Data formats
    ".tsv",
    ".psv",
    ".ndjson",
    ".jsonl",
    ".rdf",
    ".owl",
    ".ttl",
    ".n3",
    ".nt",
    ".eml",  # Email messages
    ".ics",  # Calendar files
    ".vcf",  # vCard contact files
    # Version control
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".hgignore",
    ".svnignore",
    ".dockerignore",  # Docker ignore files
    # Container/Deployment
    ".containerfile",  # Alternative to Dockerfile
    # CI/CD
    ".travis",
    ".appveyor",
    ".circleci",
    ".github",
    # Package managers
    ".npmrc",
    ".yarnrc",
    ".gemfile",
    ".podspec",
    ".nuspec",
    # IDEs/Editors
    ".editorconfig",
    ".prettierrc",
    ".eslintrc",
    ".stylelintrc",
    ".jshintrc",
    ".jscsrc",
    ".babelrc",  # Babel configuration
    ".swcrc",  # SWC configuration
    ".browserslistrc",  # Browserslist configuration
    # Logs
    ".log",
    ".out",
    ".err",
    # License/Legal
    ".license",
    ".copyright",
    # Localization/Internationalization
    ".po",  # GNU gettext
    ".pot",  # GNU gettext template
    ".strings",  # iOS/macOS strings
    ".stringsdict",  # iOS/macOS strings dictionary
    ".arb",  # Application Resource Bundle
    ".resx",  # .NET resource files
    # Other common extensions
    ".proto",  # Protocol Buffers
    ".thrift",  # Apache Thrift
    ".avro",  # Apache Avro
    ".graphql",  # GraphQL schema
    ".gql",  # GraphQL queries
    ".openapi",  # OpenAPI specifications
    ".swagger",  # Swagger specifications
    ".raml",  # RAML API specifications
    ".tpl",  # Generic template files
    ".asc",  # ASCII armor files
    ".manifest",  # Manifest files
    ".desktop",  # Linux desktop entries
    ".service",  # Systemd service files
    ".srt",  # Subtitle files
    ".vtt",  # WebVTT subtitle files
}

# Map of file extensions to programming language identifiers (lowercase for consistency)
# This covers the most common languages used in codebases
EXTENSION_TO_LANGUAGE = {
    # Python
    ".py": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".cts": "typescript",
    ".mts": "typescript",
    # Java
    ".java": "java",
    # C/C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c++": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    # C#
    ".cs": "csharp",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Ruby
    ".rb": "ruby",
    # PHP
    ".php": "php",
    # Swift
    ".swift": "swift",
    # Kotlin
    ".kt": "kotlin",
    ".kts": "kotlin",
    # Scala
    ".scala": "scala",
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    # SQL
    ".sql": "sql",
    # Web/Markup
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    # Data formats
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    # Documentation
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "markdown",
    ".rst": "restructuredtext",
    # Other languages
    ".r": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".elm": "elm",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".avro": "avro",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".openapi": "openapi",
    ".swagger": "swagger",
    ".raml": "raml",
    ".tpl": "template",
}


def is_plaintext_file(file_path: str) -> bool:
    """
    Returns True if the file is a text-based file whose text content would be useful to index.
    See PLAINTEXT_EXTENSIONS for more.
    """
    path = Path(file_path)

    if path.name.startswith("Dockerfile"):
        return True

    ext = path.suffix.lower()
    if ext in PLAINTEXT_EXTENSIONS:
        return True

    # If no extension, assume plaintext
    # This covers common files like: Makefile, makefile, GNUmakefile, Pipfile, Gemfile,
    # Rakefile, Procfile, Vagrantfile, etc.
    return not ext


def get_language_from_extension(file_path: str) -> str | None:
    """
    Detect programming language from file extension.

    Returns a lowercase language identifier (e.g., "python", "javascript")
    or None if the language cannot be determined from the extension.

    Args:
        file_path: Path to the file

    Returns:
        Language identifier (lowercase) or None if unknown
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)
