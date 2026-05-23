import 'package:flutter_test/flutter_test.dart';
import 'package:creator_algorithm_coach/main.dart';

void main() {
  testWidgets('App launches and shows navigation',
      (WidgetTester tester) async {
    await tester.pumpWidget(const CreatorAlgorithmCoachApp());
    await tester.pumpAndSettle();

    // Verify that the app renders the navigation rail
    expect(find.text('Creator Algorithm Coach'), findsOneWidget);
    expect(find.text('Dashboard'), findsWidgets);
    expect(find.text('Discover'), findsWidgets);
    expect(find.text('Publish'), findsWidgets);
    expect(find.text('Insights'), findsWidgets);
    expect(find.text('Settings'), findsWidgets);
  });
}
