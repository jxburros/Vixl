"""Slide copy and speaker notes for the autism & ADHD therapist decks.

Slides stay short (the deck check caps a page at 60 words); the detail lives in the speaker notes.
Statistics are U.S. figures from the CDC; each stats slide names its source.
"""


def theme(bg, surface, ink, muted, accent, accent_ink, accent_soft, accent2_soft, on_accent_soft, line,
          warn="#b5543c", on_warn="#ffffff", on_accent="#ffffff", bg_muted=None):
    return dict(bg=bg, surface=surface, ink=ink, muted=muted, accent=accent, accent_ink=accent_ink,
                accent_soft=accent_soft, accent2_soft=accent2_soft, on_accent=on_accent,
                on_accent_soft=on_accent_soft, line=line, warn=warn, on_warn=on_warn,
                bg_muted=bg_muted or accent_soft)


TEAL = theme("#f7f3ec", "#ffffff", "#1f3634", "#4f605d", "#2f7a72", "#23615a", "#d6ebe6", "#f3dcc8",
             "#e4f2ef", "#e7e0d4")
CLAY = theme("#faf4ee", "#ffffff", "#3a2a22", "#5f4d44", "#b4583a", "#97462c", "#f5d9cb", "#e3e8d2",
             "#fbe9e0", "#ecdfd4", warn="#5d6b3a")
BLUE = theme("#f2f5fa", "#ffffff", "#1b2a41", "#4a5871", "#2f5fa7", "#264f8c", "#d7e3f5", "#fbe3cf",
             "#e6eefa", "#dfe5ee")
PLUM = theme("#f8f4f8", "#ffffff", "#2e2135", "#5b4c63", "#7b4a8f", "#673b78", "#e8d9ef", "#fce7c4",
             "#f2e8f6", "#e8dfeb")
SAGE = theme("#f5f6f0", "#ffffff", "#1f2d22", "#4d5b50", "#3f7a52", "#326343", "#d9eadc", "#f6e0cf",
             "#e6f2e8", "#e1e5da")
NAVY = theme("#f6f4f1", "#ffffff", "#1a2238", "#4b5268", "#c4553f", "#a4412e", "#f6d8cf", "#d8e0f0",
             "#fbe8e3", "#e6e1da", warn="#3a4a74")


CARE_TEAM = {
    "slug": "01-care-team",
    "short": "Who Helps? The Autism & ADHD Care Team",
    "theme": TEAL,
    "slides": [
        {"kind": "cover", "kicker": "A guide for families, educators and adults",
         "title": "Who Helps? Therapists for Autism & ADHD",
         "subtitle": "The professionals, what each one does, and how they work together.",
         "icons": ["🧠", "💬", "🤝", "🌱"],
         "notes": "Welcome. This deck introduces the professionals who support autistic people and people "
                  "with ADHD: what each discipline focuses on, how care usually unfolds, and what good, "
                  "respectful support looks like. It is an overview, not medical advice."},
        {"kind": "stats", "title": "Why this matters",
         "stats": [("1 in 31", "U.S. 8-year-olds identified as autistic"),
                   ("11.4%", "of U.S. children aged 3–17 have ever been diagnosed with ADHD")],
         "source": "Sources: CDC Autism and Developmental Disabilities Monitoring Network (2022 data, "
                   "published 2025); CDC analysis of the 2022 National Survey of Children's Health.",
         "notes": "Autism and ADHD are common. The CDC's monitoring network found about 1 in 31 "
                  "eight-year-olds identified as autistic in 2022. About 7 million U.S. children, roughly "
                  "11 percent, have ever received an ADHD diagnosis. Many adults are also being identified "
                  "for the first time. The two often occur together, so families frequently work with "
                  "several professionals at once."},
        {"kind": "idea", "icon": "🌈",
         "text": "Autism and ADHD are differences in how a brain is wired, not problems to erase.",
         "sub": "The best therapy builds skills, comfort and independence while respecting who the person is.",
         "notes": "A neurodiversity-affirming approach treats autism and ADHD as natural variations in "
                  "development. Therapy still matters a great deal: it can ease distress, build "
                  "communication and daily-living skills, and help people get the accommodations they need. "
                  "The goal is a better life on the person's own terms, not making someone look typical."},
        {"kind": "cards", "title": "The core therapy team",
         "cards": [("✋", "Occupational therapist (OT)", "Sensory regulation, motor skills, routines and self-care."),
                   ("💬", "Speech-language pathologist", "Understanding, expression, social communication and AAC."),
                   ("🧠", "Psychologist", "Diagnostic assessment, therapy for anxiety and mood, parent coaching."),
                   ("📋", "Behavior analyst (BCBA)", "Skill-building plans; choose providers who are play-based and consent-led.")],
         "notes": "Occupational therapists help with sensory processing, handwriting, coordination and daily "
                  "routines. Speech-language pathologists work on all forms of communication, including "
                  "augmentative and alternative communication. Psychologists often lead diagnostic "
                  "evaluations and provide talk therapy such as CBT, plus parent training. Board Certified "
                  "Behavior Analysts design behavior-based skill programs; practices vary widely, so look "
                  "for naturalistic, play-based providers who respect the person's assent and avoid "
                  "compliance-focused drills."},
        {"kind": "cards", "title": "Others who often help",
         "cards": [("🩺", "Developmental pediatrician or psychiatrist", "Diagnosis, medical care and medication for ADHD or anxiety."),
                   ("🗣️", "Counselor or social worker", "Talk therapy, family support and help finding services."),
                   ("🎯", "ADHD or executive-function coach", "Planning, time and organization skills for teens and adults."),
                   ("🤸", "Physical therapist", "Strength, balance and coordination when motor skills are a challenge.")],
         "notes": "Medical doctors such as developmental-behavioral pediatricians, child psychiatrists and "
                  "neurologists diagnose, rule out other conditions, and prescribe medication when it helps. "
                  "Licensed counselors and clinical social workers provide therapy and are often skilled at "
                  "navigating services. Coaches are not licensed clinicians but can be very practical for "
                  "planning and follow-through. Physical therapists help with motor delays, low muscle tone "
                  "or coordination."},
        {"kind": "steps", "title": "How care usually unfolds",
         "steps": [("Notice", "Parents, teachers or the person spot differences."),
                   ("Screen", "A pediatrician or school does a quick check."),
                   ("Evaluate", "Specialists assess strengths and needs."),
                   ("Plan", "Goals are set together with the family."),
                   ("Support & review", "Therapy runs, progress is checked, goals update.")],
         "notes": "Most journeys start when someone notices a difference. Pediatricians screen for autism at "
                  "18 and 24 month checkups and can screen for ADHD from age 4. A full evaluation by a "
                  "psychologist, developmental pediatrician or team leads to a diagnosis and a picture of "
                  "strengths and needs. Goals should be written with the family, and with the person "
                  "themselves whenever possible, then reviewed regularly."},
        {"kind": "compare", "title": "What good care looks like",
         "columns": [("✅", "Look for", ["Builds on strengths and interests",
                                          "Respects every way of communicating",
                                          "Asks for assent and reads distress",
                                          "Treats the family as partners"], "good"),
                     ("⚠️", "Be cautious of", ["Promises of a cure or recovery",
                                                "Ignoring signs of distress",
                                                "One program for every child",
                                                "No clear goals or progress data"], "warn")],
         "notes": "Good therapists are curious about the person, use their interests to motivate learning, "
                  "accept speech, signs, pictures and devices equally, stop when someone is distressed, and "
                  "share measurable goals. Be cautious of anyone promising a cure, using expensive unproven "
                  "treatments, or pushing compliance over comfort and trust."},
        {"kind": "closing", "title": "Key takeaways",
         "items": ["Support is a team effort: each discipline covers different needs.",
                   "Start with a screening or evaluation, then set shared goals.",
                   "Choose affirming providers who respect the person and the family."],
         "note": "This overview is educational and does not replace advice from a qualified clinician.",
         "notes": "Close by reinforcing that there is no single right therapist. Families build a team over "
                  "time, and needs change with age. Invite questions and point to the other decks in this "
                  "series for detail on each discipline."},
    ],
}

OT = {
    "slug": "02-occupational-therapy",
    "short": "Occupational Therapy for Autism & ADHD",
    "theme": CLAY,
    "slides": [
        {"kind": "cover", "kicker": "Therapist spotlight",
         "title": "Occupational Therapy: Making Daily Life Work",
         "subtitle": "How OTs support sensory needs, motor skills and routines for autistic and ADHD kids and adults.",
         "icons": ["✋", "🎨", "🧦", "⏰"],
         "notes": "Occupational therapy is about occupations in the broad sense: the everyday activities "
                  "that fill a day, such as getting dressed, eating, playing, learning and working. This deck "
                  "covers what OTs do for autistic people and people with ADHD."},
        {"kind": "cards", "title": "What an OT works on",
         "cards": [("🌊", "Sensory processing", "Finding comfort with sound, touch, light and movement."),
                   ("✏️", "Motor skills", "Handwriting, scissors, buttons, balance and coordination."),
                   ("🪥", "Daily living", "Dressing, eating, hygiene, sleep and morning routines.")],
         "notes": "Many autistic people and many people with ADHD experience sensory differences: some "
                  "sensations feel overwhelming, others are sought out. OTs assess these patterns and build "
                  "strategies. They also work on fine and gross motor skills and on the self-care routines "
                  "that make school, work and home life smoother."},
        {"kind": "split", "title": "Sensory differences are real",
         "bullets": ["Noise, tags or bright light can feel painful",
                     "Some people seek movement, pressure or chewing",
                     "Overload can look like a meltdown or shutdown",
                     "Stimming often helps a person self-regulate"],
         "panel_icon": "🎧", "panel_head": "A sensory diet",
         "panel_body": "A planned set of activities through the day, such as swinging, heavy work or quiet breaks, that keeps the body regulated.",
         "notes": "Sensory differences are part of the autism diagnostic criteria and are common in ADHD. "
                  "Meltdowns are not tantrums; they are a response to overload. Harmless stimming, like "
                  "rocking or hand-flapping, usually helps regulation and should not be stopped. A sensory "
                  "diet is an individualized schedule of activities, designed with an OT, that helps the "
                  "nervous system stay in a comfortable zone."},
        {"kind": "steps", "title": "Inside an OT session",
         "steps": [("Check in", "How is the body feeling today?"),
                   ("Move", "Swings, climbing or heavy work to regulate."),
                   ("Practice", "A target skill, built into play."),
                   ("Calm down", "Quiet, deep pressure or breathing."),
                   ("Take home", "One small strategy for the week.")],
         "notes": "Sessions often look like play, and that is intentional. Movement and heavy work help "
                  "regulation, which makes it easier to learn. Skills are practiced in motivating ways, "
                  "often through the child's interests. Good OTs always send home something small and "
                  "realistic so progress carries into daily life."},
        {"kind": "cards", "title": "Executive-function supports",
         "cards": [("🗓️", "Visual schedules", "Pictures or lists show what comes next and reduce stress."),
                   ("⏳", "Visible timers", "Make time concrete for starting and switching tasks."),
                   ("🧱", "Chunking", "Break big tasks into small, finishable steps."),
                   ("🪑", "Workspace setup", "Fewer distractions, movement options and the right seat.")],
         "notes": "Executive function covers planning, starting, switching and finishing tasks, and it is a "
                  "core challenge in ADHD and for many autistic people. OTs use external supports so the "
                  "environment carries some of the load. These strategies are inexpensive and work at home, "
                  "at school and at work."},
        {"kind": "idea", "icon": "🌱",
         "text": "The goal is not to look typical. It's to make daily life comfortable and doable.",
         "sub": "Adapting the environment counts as much as building skills.",
         "notes": "An affirming OT changes the world around the person as well as teaching skills: "
                  "noise-cancelling headphones, softer clothing, a movement break or a different seat can "
                  "matter more than drills. Success is measured by comfort, participation and independence."},
        {"kind": "closing", "title": "Questions to ask an OT",
         "items": ["Which sensory or motor needs will you focus on first, and why?",
                   "How will sessions use my child's interests?",
                   "What can we practice at home between sessions?"],
         "note": "Look for the credential OTR/L (registered, licensed occupational therapist).",
         "notes": "Encourage families to ask about goals, how progress is measured and how home practice "
                  "works. In the U.S., licensed occupational therapists hold an OTR/L. Pediatric "
                  "specialists may have additional sensory integration training."},
    ],
}

SLP = {
    "slug": "03-speech-language-therapy",
    "short": "Speech-Language Therapy & Communication",
    "theme": BLUE,
    "slides": [
        {"kind": "cover", "kicker": "Therapist spotlight",
         "title": "Speech-Language Therapy & Communication",
         "subtitle": "How speech-language pathologists help autistic and ADHD people connect and be understood.",
         "icons": ["💬", "👋", "📱", "📚"],
         "notes": "Speech-language pathologists, often called SLPs or speech therapists, support every form "
                  "of communication: understanding, expressing, social interaction and literacy. This deck "
                  "covers what they do for autistic people and people with ADHD."},
        {"kind": "cards", "title": "What an SLP works on",
         "cards": [("👂", "Language", "Understanding words and sentences, and expressing needs and ideas."),
                   ("🤝", "Social communication", "Conversation, turn-taking and reading context, on the person's terms."),
                   ("📱", "Speech & AAC", "Clear speech, plus pictures, signs or devices when helpful.")],
         "notes": "SLPs assess receptive language (understanding) and expressive language (saying). Social "
                  "communication work should teach skills the person finds useful, and should respect "
                  "autistic communication styles rather than forcing eye contact or scripted small talk. "
                  "They also support speech sound clarity and introduce augmentative and alternative "
                  "communication."},
        {"kind": "idea", "icon": "🗨️",
         "text": "All communication counts: speech, signs, pictures, devices and behavior.",
         "sub": "Every person deserves a reliable way to be heard.",
         "notes": "Some autistic people speak fluently, some speak a little, some do not speak, and many "
                  "lose speech under stress. Behavior is communication too. The SLP's job is to make sure "
                  "the person has a dependable way to share needs, opinions and feelings at all times."},
        {"kind": "split", "title": "AAC: another way to talk",
         "bullets": ["Picture boards and communication books",
                     "Speech-generating apps and devices",
                     "Sign language and gestures",
                     "Useful for full-time or part-time use"],
         "panel_icon": "💡", "panel_head": "Myth: AAC stops speech",
         "panel_body": "Research shows AAC does not hold back speech, and it can support speech development. It also reduces frustration.",
         "notes": "AAC stands for augmentative and alternative communication. It ranges from simple picture "
                  "cards to sophisticated speech-generating devices. A persistent myth is that AAC prevents "
                  "people from learning to speak; studies do not support this, and AAC often supports spoken "
                  "language. Many speaking autistic adults also use AAC when tired or overwhelmed."},
        {"kind": "cards", "title": "How SLPs help with ADHD",
         "cards": [("🧭", "Following directions", "Strategies for multi-step instructions and listening."),
                   ("📖", "Storytelling & writing", "Organizing ideas into a clear beginning, middle and end."),
                   ("🔁", "Conversation flow", "Turn-taking, staying on topic and repairing misunderstandings."),
                   ("🔤", "Reading comprehension", "Tracking main ideas and details in longer texts.")],
         "notes": "Children with ADHD are more likely to have language and learning differences. SLPs help "
                  "with working-memory heavy tasks such as following directions, with narrative and written "
                  "organization, and with the pragmatics of conversation. Visual supports and graphic "
                  "organizers are common tools."},
        {"kind": "steps", "title": "Support communication at home",
         "steps": [("Model", "Use words, signs or AAC yourself."),
                   ("Wait", "Pause longer than feels natural."),
                   ("Respond", "Honor every attempt to communicate."),
                   ("Expand", "Add one word to what they said.")],
         "notes": "Family members are the most important communication partners. Modeling means using the "
                  "person's system yourself, without demanding they repeat it. Waiting gives processing "
                  "time. Responding to every attempt shows communication works. Expanding gently grows "
                  "language: if a child says 'car', you might say 'red car'."},
        {"kind": "closing", "title": "Key takeaways",
         "items": ["SLPs support every form of communication, not just speech.",
                   "AAC is a valid way to talk, and it does not stop speech.",
                   "Everyday conversations at home multiply therapy gains."],
         "note": "Look for the credential CCC-SLP (Certificate of Clinical Competence, ASHA).",
         "notes": "Summarize: communication is a right, AAC is a tool, families are partners. In the U.S., "
                  "SLPs are licensed by their state and certified by ASHA, shown as CCC-SLP."},
    ],
}

ADHD = {
    "slug": "04-adhd-therapy-and-coaching",
    "short": "ADHD: Therapy, Coaching & Skills",
    "theme": PLUM,
    "slides": [
        {"kind": "cover", "kicker": "Therapist spotlight",
         "title": "ADHD: Therapy, Coaching & Skill-Building",
         "subtitle": "The evidence-based supports that help children, teens and adults with ADHD thrive.",
         "icons": ["⚡", "🎯", "🗓️", "🏆"],
         "notes": "ADHD affects attention, activity level and impulse control, and especially executive "
                  "functions like planning and time management. This deck covers the therapies and coaching "
                  "approaches that help, and how they fit alongside medication."},
        {"kind": "stats", "title": "ADHD across the lifespan",
         "stats": [("11.4%", "of U.S. children aged 3–17 have ever been diagnosed with ADHD"),
                   ("15.5M", "U.S. adults currently have ADHD, about 1 in 16")],
         "source": "Sources: CDC analysis of the 2022 National Survey of Children's Health (2024); "
                   "CDC adult ADHD survey, MMWR (2024).",
         "notes": "ADHD is not just a childhood condition. About 7.1 million U.S. children have ever been "
                  "diagnosed, and a 2024 CDC study estimated 15.5 million adults currently have ADHD, about "
                  "half of whom were diagnosed in adulthood. Support needs change with age, from parent "
                  "training for young children to coaching and therapy for adults."},
        {"kind": "cards", "title": "Therapies that help",
         "cards": [("👪", "Parent training in behavior management", "Recommended first for children under 6."),
                   ("🧠", "Cognitive behavioral therapy", "Adapted CBT for habits, planning and stress."),
                   ("🎯", "ADHD coaching", "Goal-setting and accountability for planning and follow-through."),
                   ("🏫", "School supports", "Classroom strategies, 504 plans or IEPs.")],
         "notes": "Parent training in behavior management teaches caregivers positive, consistent strategies "
                  "and is recommended by the CDC and AAP as the first treatment for children under 6. CBT "
                  "adapted for ADHD has good evidence for adults and teens. Coaching is practical and "
                  "goal-focused. Schools can provide accommodations through a 504 plan or special education "
                  "services through an IEP."},
        {"kind": "split", "title": "Treatment works best combined",
         "bullets": ["Ages 6+: medication plus behavior therapy",
                     "Teens: add organization and study skills",
                     "Adults: CBT, coaching and workplace supports",
                     "Review the plan as needs change"],
         "panel_icon": "👶", "panel_head": "Under 6? Start with parent training",
         "panel_body": "For young children, guidelines recommend behavior therapy delivered through parents before trying medication.",
         "notes": "American Academy of Pediatrics guidance recommends that school-age children receive both "
                  "FDA-approved medication and behavioral therapy, together with classroom supports. For "
                  "preschoolers, parent training in behavior management comes first. Decisions about "
                  "medication belong to the family and their prescriber; therapy remains valuable either way."},
        {"kind": "steps", "title": "Build an executive-function routine",
         "steps": [("Externalize", "Write it down, out of your head."),
                   ("Break it down", "Next small step, not the whole task."),
                   ("Make time visible", "Timers, alarms and clocks."),
                   ("Reward", "Quick wins keep motivation going."),
                   ("Review", "Weekly reset: what worked?")],
         "notes": "ADHD makes it hard to hold plans in mind and feel future deadlines. Therapists and coaches "
                  "teach people to move information outside their head, define the very next action, make "
                  "time concrete, add near-term rewards, and hold a weekly review. These are skills anyone "
                  "can start using today."},
        {"kind": "compare", "title": "Myths and facts",
         "columns": [("✅", "Facts", ["ADHD is a neurodevelopmental difference",
                                       "It often continues into adulthood",
                                       "Therapy and medication can work together",
                                       "People with ADHD can focus deeply on interests"], "good"),
                     ("❌", "Myths", ["It's just bad behavior or laziness",
                                       "Kids always grow out of it",
                                       "Therapy means no medication",
                                       "If you can focus sometimes, it isn't ADHD"], "warn")],
         "notes": "Correct common misconceptions. ADHD is strongly heritable and linked to differences in "
                  "brain development. Many people continue to have symptoms in adulthood. Hyperfocus on "
                  "interesting tasks is common, which is why 'but they can play video games for hours' does "
                  "not rule out ADHD."},
        {"kind": "closing", "title": "Key takeaways",
         "items": ["ADHD support spans parent training, therapy, coaching and school plans.",
                   "Combine approaches, and revisit the plan as life changes.",
                   "Executive-function skills can be learned at any age."],
         "note": "This overview is educational and does not replace advice from a qualified clinician.",
         "notes": "Close by emphasizing hope and practicality: ADHD support works best as a layered, "
                  "personalized plan. Encourage people to talk with their clinician about which mix fits."},
    ],
}

FINDING = {
    "slug": "05-finding-the-right-therapist",
    "short": "Finding the Right Therapist",
    "theme": SAGE,
    "slides": [
        {"kind": "cover", "kicker": "A family guide",
         "title": "Finding the Right Therapist",
         "subtitle": "Steps, credentials and questions to help you choose support for autism and ADHD.",
         "icons": ["🔍", "🤝", "✅", "🏡"],
         "notes": "Choosing a therapist can feel overwhelming. This deck walks through the path to services, "
                  "the credentials to look for, free and school-based options, and the questions to ask so "
                  "you can find a good fit."},
        {"kind": "steps", "title": "Your path to services",
         "steps": [("Talk to your doctor", "Share concerns and ask for a referral."),
                   ("Get evaluated", "A specialist identifies strengths and needs."),
                   ("Check options", "Insurance, Medicaid, school and early intervention."),
                   ("Interview providers", "Ask questions before committing."),
                   ("Start & review", "Check progress every few months.")],
         "notes": "Start with your pediatrician or primary care provider. Waitlists for evaluations can be "
                  "long, so get on lists early and ask about cancellations. Check what your insurance or "
                  "Medicaid covers; all U.S. states now require many plans to cover autism services. "
                  "Interview more than one provider when you can."},
        {"kind": "split", "title": "Free and school-based help",
         "bullets": ["Birth to 3: Early Intervention services",
                     "Ages 3+: evaluations through your school district",
                     "IEP: special education and related therapies",
                     "504 plan: accommodations in the classroom"],
         "panel_icon": "✉️", "panel_head": "You can ask in writing",
         "panel_body": "Parents can request a free school evaluation at any time. Put the request in writing and keep a copy.",
         "notes": "Under the Individuals with Disabilities Education Act, every state runs an Early "
                  "Intervention program for infants and toddlers, and school districts must evaluate "
                  "children suspected of having a disability at no cost. Eligible students can receive "
                  "speech, occupational and other therapies through an IEP. A 504 plan provides "
                  "accommodations such as extra time or movement breaks."},
        {"kind": "cards", "title": "Credentials to look for",
         "cards": [("✋", "OTR/L", "Licensed occupational therapist."),
                   ("💬", "CCC-SLP", "Certified, licensed speech-language pathologist."),
                   ("🧠", "PhD or PsyD", "Licensed psychologist; can diagnose and provide therapy."),
                   ("🗣️", "LCSW or LPC", "Licensed clinical social worker or professional counselor.")],
         "notes": "Credentials show training and accountability to a licensing board. Behavior analysts hold "
                  "a BCBA certification and, in many states, a license. Coaches are not licensed clinicians, "
                  "which is fine for practical skills but means they should not treat mental-health "
                  "conditions. You can verify licenses on your state's licensing board website."},
        {"kind": "cards", "title": "Questions to ask a provider",
         "cards": [("🎯", "How do you set goals?", "Listen for goals written with you and your child."),
                   ("🗨️", "How do you include my child's voice?", "Assent, choice and interests should matter."),
                   ("👀", "What does a session look like?", "Ask to observe, or watch a short video."),
                   ("📈", "How will we know it's working?", "Expect clear measures and regular reviews.")],
         "notes": "These questions reveal a provider's philosophy. Strong answers mention collaboration, "
                  "the child's assent and preferences, transparency about methods, and measurable progress. "
                  "Be wary of vague answers or reluctance to let parents observe."},
        {"kind": "compare", "title": "Green flags and red flags",
         "columns": [("✅", "Green flags", ["Welcomes questions and observation",
                                             "Celebrates strengths and stims",
                                             "Adjusts when your child is upset",
                                             "Shares progress data openly"], "good"),
                     ("🚩", "Red flags", ["Promises a cure or fast fix",
                                           "Keeps parents out of sessions",
                                           "Pushes on through distress",
                                           "Sells costly, unproven treatments"], "warn")],
         "notes": "Trust your instincts. A good fit feels collaborative and your child should, over time, "
                  "look forward to sessions. Treatments such as chelation or bleach-based protocols are "
                  "dangerous and have no evidence; steer clear of anyone recommending them."},
        {"kind": "idea", "icon": "🏡",
         "text": "You know your child best. A good therapist treats you as a partner.",
         "sub": "If it doesn't feel right after a fair try, it's okay to change providers.",
         "notes": "Families are experts on their own child. A strong therapeutic relationship is one of the "
                  "best predictors of progress. Changing providers is normal and not a failure."},
        {"kind": "closing", "title": "Your next steps",
         "items": ["Write down your concerns and your child's strengths.",
                   "Ask your doctor and school about evaluations this week.",
                   "Interview two providers using the questions in this deck."],
         "note": "This overview is educational and does not replace advice from a qualified clinician.",
         "notes": "End with concrete actions. Remind families that waitlists are common, so starting the "
                  "process early helps, and that school and early intervention services are free."},
    ],
}

ADULTS = {
    "slug": "06-therapy-for-adults",
    "short": "Therapy for Autistic & ADHD Adults",
    "theme": NAVY,
    "slides": [
        {"kind": "cover", "kicker": "Support beyond childhood",
         "title": "Therapy for Autistic & ADHD Adults",
         "subtitle": "Late diagnosis, burnout, work and relationships: the support that helps grown-ups thrive.",
         "icons": ["🧭", "💼", "☕", "🔋"],
         "notes": "More adults than ever are being identified as autistic or as having ADHD, often after a "
                  "child's diagnosis or a period of burnout. This deck covers therapy and support options "
                  "built for adults."},
        {"kind": "idea", "icon": "🧭",
         "text": "It's never too late to understand how your brain works.",
         "sub": "A diagnosis in adulthood can bring relief, self-compassion and better support.",
         "notes": "Many adults describe a late diagnosis as making sense of their whole life. It can unlock "
                  "accommodations at work and school, connection with community, and therapy that finally "
                  "fits. Self-identification is valid too, though a formal diagnosis may be needed for some "
                  "accommodations or medication."},
        {"kind": "cards", "title": "Support that helps adults",
         "cards": [("🌈", "Affirming psychotherapy", "Therapists who understand neurodivergence, masking and identity."),
                   ("🧠", "Adapted CBT", "Concrete, structured tools for anxiety, habits and planning."),
                   ("🎯", "ADHD coaching", "Accountability for routines, projects and time management."),
                   ("✋", "Occupational therapy", "Sensory needs, daily routines and workplace setup.")],
         "notes": "Look for therapists who explicitly work with neurodivergent adults. Standard therapy can "
                  "miss the mark if it assumes neurotypical communication or treats traits as symptoms to "
                  "fix. CBT adapted for autism and ADHD is more concrete and visual. Adult OT is "
                  "underused but valuable for sensory and routine challenges."},
        {"kind": "split", "title": "Common goals in adult therapy",
         "bullets": ["Recovering from burnout",
                     "Managing anxiety and depression",
                     "Executive function at work and home",
                     "Relationships and self-advocacy"],
         "panel_icon": "🔋", "panel_head": "Masking and burnout",
         "panel_body": "Hiding traits to fit in takes energy. Over time it can lead to exhaustion; therapy helps people unmask safely and pace themselves.",
         "notes": "Autistic burnout is a state of deep exhaustion and reduced coping, often after long periods "
                  "of masking and sensory overload. Anxiety and depression are common in both autistic and "
                  "ADHD adults. Therapy can help people find sustainable routines, set boundaries, and "
                  "advocate for what they need."},
        {"kind": "steps", "title": "Getting started as an adult",
         "steps": [("Reflect", "Notice patterns across your life."),
                   ("Find an assessor", "Choose one who sees adults."),
                   ("Get assessed", "Interviews, history and questionnaires."),
                   ("Plan supports", "Therapy, coaching or medication."),
                   ("Ask for adjustments", "Request changes at work or school.")],
         "notes": "Adult assessments are usually done by psychologists or psychiatrists experienced with "
                  "adults; ask specifically about that experience. Bring examples from childhood if you can. "
                  "In the U.S., the Americans with Disabilities Act lets employees request reasonable "
                  "accommodations such as flexible hours, quieter workspaces or written instructions."},
        {"kind": "closing", "title": "Key takeaways",
         "items": ["Adult diagnosis is common, and support is available.",
                   "Choose therapists who understand neurodivergent adults.",
                   "Pace yourself: rest and accommodations are part of the plan."],
         "note": "This overview is educational and does not replace advice from a qualified clinician.",
         "notes": "Close by validating adults who are exploring diagnosis and support. Encourage connecting "
                  "with neurodivergent-led communities alongside professional help."},
    ],
}

DECKS = [CARE_TEAM, OT, SLP, ADHD, FINDING, ADULTS]
