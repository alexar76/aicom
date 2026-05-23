import 'package:flutter_test/flutter_test.dart';
import 'package:interview_prep_coach/main.dart';

void main() {
  testWidgets('App launches and shows loading state', (tester) async {
    await tester.pumpWidget(const InterviewPrepCoachApp());
    // The app should show a loading indicator on first launch.
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
