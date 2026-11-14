# Third-party software

| Component | License | Use |
|---|---|---|
| [acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp) (git submodule) | MIT | native music engine (ace-synth, ace-lm) |
| [ggml](https://github.com/ggml-org/ggml) (inside acestep.cpp) | MIT | tensor library |
| yyjson, cpp-httplib (inside acestep.cpp) | MIT | JSON parsing (httplib is not built for the app) |
| [Chaquopy](https://chaquo.com/chaquopy/) | MIT | Python runtime in the app |
| [NumPy](https://numpy.org/) | BSD-3-Clause | analysis in Python |
| AndroidX, Jetpack Compose, Kotlin coroutines | Apache-2.0 | app framework |

## Model weights (not part of this repository)

The app downloads, after the user's confirmation, GGUF conversions of the ACE-Step 1.5 models from
[Serveurperso/ACE-Step-1.5-GGUF](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF) (MIT, original weights by
ACE Studio and StepFun, [ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5)).
No model files are stored in this repository.
