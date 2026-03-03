from openai import OpenAI
from datetime import datetime

client = OpenAI(
    api_key="sk-N2OOLFzETy3KmZuFSnlFHQ8iko5vhnLYFbuwnKF47jiqE5fm",
    base_url="https://max.openai365.top/v1"
)

# Read the paper content
with open('/data0/home/scli/Codes/OpenAIglasses_for_Navigation-main/latex/main.tex', 'r') as f:
    paper_content = f.read()

# Output file with timestamp
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
output_file = '/data0/home/scli/Codes/OpenAIglasses_for_Navigation-main/api_chat/review.md'

# Prepare the review prompt
review_prompt = """You are a world-leading expert in the field of assistive technology, computer vision for robotics, and edge computing.

The following text is a LaTeX draft of a paper intended for submission to IROS (IEEE/RSJ International Conference on Intelligent Robots and Systems), a top-tier robotics conference.

Please review this manuscript with the MOST CRITICAL, HARSH, STRICT, and MEAN perspective possible - like a picky IROS reviewer who rejects most papers.

Focus your review on:
1. Technical soundness and novelty
2. Clarity of the contribution and presentation
3. Experimental evaluation methodology
4. Comparison with prior art (especially edge-based assistive systems)
5. Writing quality and logical flow

CRITICAL INSTRUCTIONS:
- Be extremely critical - point out EVERY weakness
- Question claims that lack proper evidence
- Highlight vague or hand-wavy descriptions
- Point out missing baselines or ablation studies
- Criticize overstatements or exaggerated claims
- Check if the contribution is truly significant enough for IROS

Please write your review in the following format:

---
Overall Merit: (4-point scale: 1=Accept, 2=Weak Accept, 3=Weak Reject, 4=Reject)

Paper Summary: (1-2 paragraphs summarizing what the paper claims to do)

Strengths: (2-3 bullet points - be sparing, only genuine strengths)

Weaknesses: (4-6 bullet points - be thorough and harsh)
- [Specific technical issue]
- [Missing experimental validation]
- [Unclear writing or logic gap]
- [Overstated claim]
- ...

Subjective Evaluation:
(Detailed assessment covering:
- Is the contribution significant enough for IROS?
- Are the experiments sufficient? What's missing?
- Is the comparison with prior work fair and complete?
- Are the claims properly supported by evidence?
- Specific questions for the authors to address
- Recommended improvements if revision were possible)

---

PAPER CONTENT (LaTeX format):
"""

review_prompt += paper_content

try:
    print("Sending paper to Gemini 3 Pro for review...")
    print("=" * 60)

    response = client.chat.completions.create(
        model="gemini-3-pro-preview-thinking",
        messages=[
            {"role": "user", "content": review_prompt}
        ],
        temperature=0.7,
        max_tokens=4096
    )

    review_content = response.choices[0].message.content

    # Print to console
    print(review_content)
    print("=" * 60)
    print("\nReview completed!")

    # Write to file with timestamp
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# IROS Paper Review\n\n")
        f.write(f"**Review Time:** {timestamp}\n")
        f.write(f"**Paper:** Open-world Active Description for People with Visual Impairments\n")
        f.write(f"**Reviewer:** Gemini 3 Pro (gemini-3-pro-preview-thinking)\n\n")
        f.write("---\n\n")
        f.write(review_content)

    print(f"\nReview saved to: {output_file}")

except Exception as e:
    print(f"Request failed: {e}")

    # Save error to file as well
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# IROS Paper Review - ERROR\n\n")
        f.write(f"**Time:** {timestamp}\n")
        f.write(f"**Error:** {str(e)}\n")
