# IROS Paper Review

**Review Time:** 2026-01-26 07:22:45
**Paper:** Open-world Active Description for People with Visual Impairments
**Reviewer:** Gemini 3 Pro (gemini-3-pro-preview-thinking)

---

Here is the review of the manuscript.

---

**Overall Merit:** 4 (Reject)

**Paper Summary:**
The authors propose an "edge-native" wearable assistive navigation system for people with visual impairments (PVI), utilizing an NVIDIA Jetson Orin Nano and a wide-angle camera. The system aims to address the latency issues of cloud-based Multimodal Large Language Models (MLLMs) by performing all computations locally. The core contribution is described as a "task-aware information prioritization" module, which uses YOLOE for object detection followed by a heuristic re-ranking process based on manually defined weights (task, scene, user preference) and IMU-based head movement suppression. The authors claim this system reduces redundant audio feedback and cognitive load compared to a "broadcast" baseline and a cloud-based MLLM.

**Strengths:**
*   **Practical Hardware Integration:** The system integration of the Jetson Orin Nano, camera, and bone-conduction headphones is a functional, albeit standard, engineering implementation of a wearable aid.
*   **Latency Focus:** The premise of prioritizing deterministic edge-based latency over non-deterministic cloud inference is valid and critical for safety-related assistive technologies.

**Weaknesses:**
*   **Trivial and Archaic Methodology:** The core technical contribution (Section IV-B) is scientifically inadequate for a top-tier conference like IROS. Equation (1) is simply a multiplication of detection confidence by manually tuned, hard-coded scalar weights stored in lookup tables. This is not "AI" or "Robotics research"; it is basic rule-based scripting. There is no learning component, no optimization framework, and no theoretical grounding for how these weights are derived other than "domain knowledge."
*   **Unacceptable Strawman Baselines:** The experimental comparison is fundamentally flawed. Comparing the proposed system against a "Local Broadcast" baseline (which announces *every* raw detection frame-by-frame) is intellectually dishonest. No existing assistive system operates that way; it is a strawman designed to make the proposed method look good. The comparison should be against state-of-the-art tracking-based filters (e.g., DeepSORT with Kalman filtering) or existing open-source navigation aids (e.g., NavCog, Sound of Vision), not a naive implementation that no one would ever use.
*   **Dangerous Heuristics:** The "Proprioceptive Closed-loop Feedback" (Section IV-E) is dangerously flawed. Suppressing audio output when the yaw rate exceeds 25 deg/s assumes that head movement implies a lack of need for information. In reality, PVI users actively scan their environment by turning their heads to localize sound sources or check crosswalks. Muting the system during this active scanning phase defeats the purpose of an assistive device.
*   **Incomplete Manuscript:** The draft contains multiple placeholders (e.g., "\todo{XX} milliseconds," "User studies with \todo{N} participants," "\todo{Replace with actual system architecture diagram}"). Submitting a paper with missing data and incomplete figures is unprofessional and grounds for immediate desk rejection.
*   **Lack of Scene Understanding Robustness:** The scene inference mechanism is described as a "heuristic voting scheme" (Section IV-B-2). This is exceptionally brittle. If a user is indoors but walks past a poster of a car, or looks out a window, the system might hallucinate a "street" context and change its weighting parameters entirely. There is no temporal consistency check or probabilistic modeling.
*   **Incremental Engineering vs. Research:** This paper represents a system integration effort (putting YOLOE on a Jetson) rather than a methodological contribution. The "Task-Specific Engine Loading" is just standard software engineering (loading different config files), not a scientific contribution.

**Subjective Evaluation:**

This paper is nowhere near the standard required for IROS. It reads like an undergraduate capstone project report rather than a serious research contribution in robotics and computer vision.

**1. Significance and Novelty:**
The novelty is virtually non-existent. Running object detection on a Jetson is standard practice. The "prioritization algorithm" is a set of `if-then` statements and magic numbers (weights) that the authors admit are "manually tuned." In an era of End-to-End learning, Reinforcement Learning, and sophisticated Bayesian filtering, proposing a hard-coded lookup table ($W_{task}$, $W_{scene}$) as a primary contribution is unacceptable.

**2. Experimental Validity:**
The experiments are essentially meaningless due to the weak baselines.
*   **Latency:** Comparing edge computing to cloud computing for latency is trivial. We know edge is faster. The question is: is the *drop in semantic quality* worth the speed gain? The paper fails to quantify the accuracy trade-off compared to the MLLM.
*   **Filtering:** The "Redundancy reduction" metric is easily gamed. I could achieve 100% redundancy reduction by turning the device off. The paper needs to measure "Information Transfer Rate" or "Situation Awareness" properly, not just how many bounding boxes were deleted.
*   **User Study:** The placeholders (\todo{N}) imply the study might not even be finished. Furthermore, the "Broadcast" baseline is so annoying that *any* filtering would result in a better NASA-TLX score. This does not prove the proposed heuristic is good; it only proves that screaming every detection at a user is bad.

**3. Specific Questions/Issues for Authors:**
*   **Weight Tuning:** How exactly were the weights in Eq. 1 derived? If you move to a new city or a different country with different street furniture, does the system fail? Do you have to manually re-tune the CSV files? This lacks generalization.
*   **Safety Criticality:** Regarding the IMU gating—if a silent electric vehicle approaches from the side while the user is turning their head (yaw > 25 deg/s) to check for traffic, your system suppresses the warning. How do you justify this safety risk?
*   **Comparison:** Why did you not compare against a standard tracker (e.g., ByteTrack or DeepSORT) which naturally handles deduplication and ID persistence? This is the standard solution for the "redundancy" problem, not heuristic throttling.

**Recommendation:**
The paper requires a complete overhaul. The heuristic weight system should be replaced with a learned policy (e.g., Imitation Learning from human guides or RL). The baselines must be realistic. The safety logic regarding head movements needs to be re-thought entirely. As it stands, this is a clear Reject.