# Contributing

## Development Setup

### Prerequisites

- Flutter SDK 3.11+ with desktop support
- Dart SDK 3.11+
- A wallet for the AI Market (created during first-launch wizard)

### Getting Started

```bash
# Clone the repo
git clone https://github.com/alexar76/interview-prep-coach.git
cd interview-prep-coach

# Get dependencies
flutter pub get

# Run tests
flutter test

# Run the app (Linux)
flutter run -d linux

# Run the app (macOS)
flutter run -d macos

# Run the app (Windows)
flutter run -d windows
```

### Local SDK Development

If you are also making changes to the `aimarket_agent` Dart SDK, use the path dependency:

```yaml
dependencies:
  aimarket_agent:
    path: ../aimarket-sdks/dart
```

This is already configured in `pubspec.yaml`.

## Code Style

This project follows Flutter's recommended lint rules. See `analysis_options.yaml` for the full list.

Key conventions:
- Use `const` constructors where possible
- Prefer named parameters for constructors with 2+ params
- Use `camelCase` for variables and methods
- Use `PascalCase` for types and classes
- Sort imports: Dart SDK > Flutter SDK > third-party > project
- One class per file unless classes are tightly coupled

## Pull Request Process

1. Create a feature branch from `main`.
2. Make your changes.
3. Run `flutter test` — all tests must pass.
4. Update documentation if needed.
5. Create a pull request with a clear title and description.
6. A maintainer will review your PR.

## Commit Messages

Follow conventional commits:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation
- `test:` — tests
- `refactor:` — code refactoring
- `chore:` — maintenance

## Code of Conduct

Be respectful, constructive, and inclusive. See our full Code of Conduct in the repository root.
