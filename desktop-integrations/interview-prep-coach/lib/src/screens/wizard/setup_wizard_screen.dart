import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/app_state.dart';
import '../../services/wallet_service.dart';
import '../../services/marketplace_service.dart';
import '../../theme/app_theme.dart';

/// First-launch setup wizard.
///
/// Walks the user through:
/// 1. Welcome and product overview
/// 2. Wallet creation/import
/// 3. Target company and role selection
class SetupWizardScreen extends StatefulWidget {
  const SetupWizardScreen({super.key});

  @override
  State<SetupWizardScreen> createState() => _SetupWizardScreenState();
}

class _SetupWizardScreenState extends State<SetupWizardScreen> {
  final _pageController = PageController();
  int _currentPage = 0;

  // Form state.
  String _company = '';
  String _role = '';
  bool _walletReady = false;
  bool _isSettingUp = false;
  String? _error;

  static const _companies = [
    'Google',
    'Meta',
    'Amazon',
    'Apple',
    'Microsoft',
    'Netflix',
    'Stripe',
    'Airbnb',
    'Uber',
    'Tesla',
  ];

  static const _roles = [
    'Software Engineer',
    'Senior Software Engineer',
    'Staff Engineer',
    'Engineering Manager',
    'Product Manager',
    'Data Scientist',
    'Machine Learning Engineer',
    'DevOps / SRE',
    'Frontend Engineer',
    'Backend Engineer',
  ];

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _setupWallet() async {
    setState(() => _isSettingUp = true);
    try {
      final wallet = context.read<WalletService>();
      await wallet.initialize();
      if (!mounted) return;
      setState(() {
        _walletReady = true;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _isSettingUp = false);
    }
  }

  Future<void> _finishSetup() async {
    if (_company.isEmpty || _role.isEmpty) return;

    setState(() => _isSettingUp = true);
    try {
      final appState = context.read<AppState>();
      await appState.setTarget(company: _company, role: _role);
      try {
        await context.read<MarketplaceService>().ensureChannel();
        appState.setMarketplaceConnected(true);
      } catch (_) {
        // Hub may be offline in local demo — onboarding still completes.
        appState.setMarketplaceConnected(false);
      }
      await appState.completeOnboarding();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _isSettingUp = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Progress indicator.
            LinearProgressIndicator(
              value: (_currentPage + 1) / 3,
              backgroundColor: Colors.grey.shade200,
            ),
            Expanded(
              child: PageView(
                controller: _pageController,
                onPageChanged: (i) => setState(() => _currentPage = i),
                children: [
                  _buildWelcomePage(),
                  _buildWalletPage(),
                  _buildTargetPage(),
                ],
              ),
            ),
            // Bottom navigation.
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  if (_currentPage > 0)
                    TextButton(
                      onPressed: () =>
                          _pageController.previousPage(
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeInOut,
                          ),
                      child: const Text('Back'),
                    )
                  else
                    const SizedBox.shrink(),
                  FilledButton(
                    onPressed: _currentPage < 2
                        ? () {
                            if (_currentPage == 1 && !_walletReady) {
                              _setupWallet();
                              return;
                            }
                            _pageController.nextPage(
                              duration: const Duration(milliseconds: 300),
                              curve: Curves.easeInOut,
                            );
                          }
                        : _finishSetup,
                    child: Text(
                      _currentPage == 2
                          ? 'Start Preparing'
                          : _currentPage == 1 && !_walletReady
                              ? 'Setup Wallet'
                              : 'Continue',
                    ),
                  ),
                ],
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildWelcomePage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.school,
            size: 64,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 24),
          Text(
            'Welcome to\nInterview Prep Coach',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 16),
          Text(
            'Your AI-powered interview preparation companion.\n\n'
            'Access company-specific question banks updated weekly.\n'
            'Practice with real questions reported by candidates.\n'
            'Track your progress and improve with AI feedback.\n\n'
            'All powered by the AI Market decentralized protocol.',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  height: 1.5,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildWalletPage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            _walletReady ? Icons.check_circle : Icons.account_balance_wallet,
            size: 64,
            color: _walletReady
                ? Colors.green
                : Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 24),
          Text(
            'Marketplace Wallet',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 16),
          Text(
            _walletReady
                ? 'Your wallet is ready. You can discover and purchase '
                    'interview question banks from the marketplace.'
                : 'To use the marketplace, you need a wallet. '
                    'This enables you to buy question banks and sell '
                    'anonymized interview data.\n\n'
                    'Your wallet key stays on your device.',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  height: 1.5,
                ),
          ),
          if (_walletReady) ...[
            const SizedBox(height: 24),
            Card(
              child: ListTile(
                leading: const Icon(Icons.key),
                title: const Text('Wallet Address'),
                subtitle: Text(
                  context.read<WalletService>().address ?? 'Unknown',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ),
          ],
          if (_isSettingUp) ...[
            const SizedBox(height: 24),
            const Center(child: CircularProgressIndicator()),
          ],
        ],
      ),
    );
  }

  Widget _buildTargetPage() {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Target',
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Which company are you preparing for?',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 8),
          Autocomplete<String>(
            optionsBuilder: (textEditingValue) {
              if (textEditingValue.text.isEmpty) return _companies;
              return _companies.where((c) =>
                  c.toLowerCase().contains(textEditingValue.text.toLowerCase()));
            },
            onSelected: (v) => _company = v,
            fieldViewBuilder: (context, controller, focusNode, onSubmit) {
              return TextField(
                controller: controller,
                focusNode: focusNode,
                decoration: const InputDecoration(
                  hintText: 'e.g. Google, Meta, Amazon',
                  prefixIcon: Icon(Icons.business),
                ),
              );
            },
          ),
          const SizedBox(height: 16),
          Text(
            'What role?',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 8),
          Autocomplete<String>(
            optionsBuilder: (textEditingValue) {
              if (textEditingValue.text.isEmpty) return _roles;
              return _roles.where((r) =>
                  r.toLowerCase().contains(textEditingValue.text.toLowerCase()));
            },
            onSelected: (v) => _role = v,
            fieldViewBuilder: (context, controller, focusNode, onSubmit) {
              return TextField(
                controller: controller,
                focusNode: focusNode,
                decoration: const InputDecoration(
                  hintText: 'e.g. Software Engineer, Product Manager',
                  prefixIcon: Icon(Icons.work),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}
