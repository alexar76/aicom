Following up on approval fatigue: the prompt now names the action, shows destination arguments and explains why the guard asks, with recognized sensitive values redacted. It does not claim a destination came from `list_channels` unless that relationship was actually tracked; a fingerprint warning also says when its matching source was not retained.

We still have no measured human approval rate, reading time or fatigue result. The historical 39/97 counts tasks that triggered an ask, not people who approved it.

The wrap path can record an explicit elicitation response such as accept, decline or cancel. That is better than inferring approval from subsequent execution, but a scripted client can produce the same response, so our test replies are not human observations. Hook-only tool execution remains insufficient evidence that someone clicked Allow.

A useful rate needs a denominator of approval requests actually presented to people, with their responses linked to those requests; timeouts, cancellations, proxy refusals and audit-only decisions need separate counts. Until we have those data, I won’t turn the ask rate into an approval rate or claim the clearer prompts reduced fatigue.
