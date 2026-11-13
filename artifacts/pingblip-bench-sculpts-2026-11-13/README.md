# PingBlip sculpt release on Game, Forge, and World

Release commit: `89ed03abf5f0e59d04ffd94d10185868d9eb7455`

The November 11 rollout updated Forge and World. The game serves its own copies
of the GLBs and previews, and its compiled client includes its own model-version
manifest. Before this release, the public game returned all 57 previous files
for the 19 corrected figurines. Forge and World returned the corrected files.

For Glaze Donut, the previous asset had four individual cone meshes
(`Glaze drip.0` through `.3`). The corrected asset has a continuous
`Thick pink glaze` mesh with rounded drips. The Bench browser check uses a
fixture for the evolved Donut and intercepts player API calls.

The game release overlays 19 GLBs and 38 previews from the commit onto the
previous production game image and rebuilds the Next.js output so the client
requests the new model versions. It uses the existing game deployment
configuration. The previous image is retained as
`pingblip-pingblip:before-sculpts-20261113-89ed03abf`.

The initial image build stalled on base-layer extraction. The successful build
used a network-isolated staging container created from the same image, then
compared the candidate's runtime configuration to the original image before
switching the game service. The candidate matched the expected hashes for all
57 files, and all 19 model versions were present in the new browser bundle.

After the switch, all 133 public asset requests matched the release hashes.
The [deployment receipt](deployment.txt), [build log](build-stage.log), and
[public asset report](public-assets-after.json) record the results.
