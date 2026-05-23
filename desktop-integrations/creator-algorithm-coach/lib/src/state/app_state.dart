import 'package:flutter/foundation.dart';

/// Application-wide state for the Creator Algorithm Coach.
class AppState extends ChangeNotifier {
  String _activePlatform = 'tiktok';
  String _niche = '';
  double _budgetUsd = 5.00;
  bool _isMarketplaceConnected = false;
  String? _walletAddress;
  String _hubUrl = 'https://hub.aicom.io';

  String get activePlatform => _activePlatform;
  String get niche => _niche;
  double get budgetUsd => _budgetUsd;
  bool get isMarketplaceConnected => _isMarketplaceConnected;
  String? get walletAddress => _walletAddress;
  String get hubUrl => _hubUrl;

  set activePlatform(String value) {
    _activePlatform = value;
    notifyListeners();
  }

  set niche(String value) {
    _niche = value;
    notifyListeners();
  }

  set budgetUsd(double value) {
    _budgetUsd = value;
    notifyListeners();
  }

  void setMarketplaceConnected(String address) {
    _isMarketplaceConnected = true;
    _walletAddress = address;
    notifyListeners();
  }

  void disconnectMarketplace() {
    _isMarketplaceConnected = false;
    _walletAddress = null;
    notifyListeners();
  }
}
