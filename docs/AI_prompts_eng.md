# AI prompts log (Final Project: Rentrail)

> Korean original: [AI_prompts.md](AI_prompts.md)

I built this project with the coding agent **Claude Code**. Below are the prompts I typed during the Final
Project, in time order, translated from Korean (the originals are in `AI_prompts.md`). Material I pasted in
(the assignment page, the TA's announcement) is not my writing, so it is only summarized as `[pasted: …]`.
The line under each prompt says what changed as a result.

- The app itself calls one model at run time, `gpt-6-luna` on the course key, as the rules require.
- I decided the topic, the scope, the demo story (timeline), the design direction, the safety principles and the
  submission choices; Claude Code wrote the implementation, tests and document drafts, which I reviewed.

---

## 1. Ideation (Oct 13–15)

**#1 · Oct 13**
> Final Project (Ideation)

**#2 · Oct 13**
> First we need to pick the Final Project topic — it's a free topic. Let me dump the Final Project page for you.
> https://zlisto.github.io/mgt_409_fa26/project_requirements.html
> I think you can see the whole thing. Read it carefully, understand it, and remember it until the end of the project.

→ Saved the full requirements as `project_requirements.md` and summarized the rubric.

**#3 · Oct 13**
> I was thinking of my Pawprints project, but it feels a bit obvious. Alternatively, a service for settling in the U.S. could be good — a full package, personalized for each person.

**#4 · Oct 14**
> That too — and in Korea as well, finding a home, signing up for internet and electricity/water, getting a phone number: all of these steps were uncertain and hard. Is it too big?

→ Trip planners are on the assignment's "overdone" list; all of settling-in was too big, so the scope narrowed to renting.

**#5 · Oct 15**
> Can you see the conversation "AI Foundation Final Project topic discussion"?

**#6 · Oct 15**
> [pasted: the project brief I wrote in an earlier Claude chat — topic "tenant-side rent management agent", four candidate agents, MVP scope, competitors, Tier 3 strategy, next steps]

→ Topic confirmed: tenant-side, from move-in to move-out. Wrote `topic_brief.md` and `plan.md`.

**#7 · Oct 15**
> I put them in @2_Final Project/data. The photos are actually of damage that happened while moving after I moved in, which is why I kept them. We could generate photos without the damage for "before move-in" and use the originals with the damage as "after". I also put the lease and insurance documents for my home in data.
>
> A few more things: it would be good to support video as well as photos, and before building anything, let's talk more about the overall plan and outline.

→ My real photos and videos became the evidence; the move-in photos are edited copies with the defect removed (named `EDITED_…`).

**#8 · Oct 15**
> [pasted: part of Claude's previous answer, "making photos with the damage removed"]
>
> Couldn't you do this by connecting to OpenAI through the Port Key?
>
> 1. Good.
> 2. Yes, I submitted it.
> 3. I'd still like you to do it. I don't think it's too big, and a simple before/after photo comparison feels too simple. I really want to build an agent that gives full coverage from move-in to move-out.
> 4. Good!

→ The course key allows only gpt-6-luna (no image-generation model), so the edits were done in code. Scope: the whole lease lifecycle.

**#9 · Oct 15**
> I'll do #1 later, I'm out right now.
> I put in #2.
> There is no #3...
> For #4, please recommend something.

**#10 · Oct 15**
> Let's go with MoveProof, start the competitor research.

**#11 · Oct 15**
> Let's call it Rentrail and add Korean support too. Do other apps have a sublet feature? The goal is to cover both the person subletting out and the person subletting in.

→ An app named "MoveProof" already exists, so **Rentrail**. Researched 15 competitors (`research/competitors.md`); none serves both sides of a sublet.

## 2. Design and first build (Oct 20)

**#12 · Oct 20**
> CT matters, but reflecting every region's differences would be too much, right? Shall we do CT only for now? And if we really built a business on this, it would be good for us to keep the deposit and later split it between tenant and owner according to the dispute result. It would be good to make this settlement work too, with a simulated card payment or bank transfer (not real payments, of course). It's fun to show. Is anything else needed now? Or is it doable? Also login, privacy protection — photos and videos can contain personal information too, so protect those well — and all of the items below must be explained, so keep them in mind. What do you think? Which tier would it be, and what score?
>
> [pasted: the assignment's slide outline 1–9]

→ Connecticut law only. Escrow settlement with simulated payments, login, and privacy (photo GPS removal, face blur, name masking) became part of the design.

**#13 · Oct 20**
> It doesn't have to be deployed to get real users. I can try it myself. Make the sublet deposit a real feature. Make the lease deposit a business vision. What is the insurance question in P2? I put the videos in @2_Final Project/data. For now I marked a crack with a whiteboard marker at school. Just assume before/after.

→ The sublet escrow is a working feature; holding the main lease deposit is the business vision. A marker-drawn crack is stated as a demo convention.

**#14 · Oct 20**
> I also put "Crack - AI no report" in @2_Final Project/data. Build it. Pay close attention to how the graders will run it (below). I'm thinking of option 2, but I'll prepare both 1 and 2. If I do 1, I'll put it on Render.
>
> Make the website layout intuitive and well organized. Since it targets Yale students, make good use of the Bulldogs in @99_Assets for the website images. Bulldogs dressed up like police guarding you would be nice, and since in the end I'm the one making a judgement, a Chief Justice Bulldog would be good too. We should also make good use of what we did in the lectures and homeworks. Showing the agents would be good — token usage, what the agents send each other when they call one another, and a Boss agent. We did video and photo comparison in class too; build the website well. I'd also like reviews, Q&A and shared stories. Let's go!!
>
> [pasted: the assignment's "Testing the app" section]

→ First version: six bulldog agents (Chief Justice Dan = Boss), the Agent Room (tokens and calls), photo/video comparison, community, the "instruction to the AI inside a photo" safety test, local run plus a Render config.

## 3. Feedback and improvement (Oct 20–22)

**#15 · Oct 20**
> Isn't it a bit complicated? First, the text is too long. Upcoming deadlines would be better as a table: item, amount, days left. When I open "Ask Chief Justice Dan", nothing shows and it seems to break. And when I log in as a tenant, sublet/escrow should be hidden or disabled. I'd like a chatbot agent on Home that I can ask things right away, that takes actions, and that moves me around the site. Without it the Agent Room and the agent introductions feel meaningless. Also, in the After video there's a crack, and I filmed the same spot with nothing there in the Before video, but the video analysis doesn't catch it.

→ Deadlines as tables, role-based menus, an action-taking chatbot (tools to open pages and start work), the chat page fixed, and same-spot before/after frame pairing.

**#16 · Oct 20**
> The escrow ledger shows today's real date; it should show the app's simulated date. Also add a ledger reset. Why doesn't the subtenant have the lease feature, utility bill payments and records (does the sublessor usually pay these? does it depend on the contract?), or the deposit court? Also, the sublease and the regular lease are currently identical — make a fictional sublease and update it. And when I test by moving the time machine, everything stays the same: there's already damage listed before the sublet even started. Make it realistic. The quality is too low right now, especially the backend.

→ Every record and payment now uses the simulated date, and moving the date shows only what exists by then. Separate sublease; lease, bills and an appeal court for the subtenant.

**#17 · Oct 20 (asked during the work)**
> Also — answer this after you finish everything you're doing — in the agent hierarchy there's a police officer before the Boss. Is that right? Shouldn't the Boss decide, call the officer to clean the data, and send it to the other agents?

**#18 · Oct 21**
> Then don't make the officer a Dan; make it feel like some kind of inspection. Less like one agent, more like a checkpoint.

→ The safety layer was redesigned as a code "Checkpoint" that even the Boss cannot skip (not an agent).

**#19 · Oct 21**
> Alex Kim doesn't have the sublease. And Alex Kim's inspection records should be based on the photos and video I took at my original move-in and the ones I took at move-out. At move-in there should be no damage. Precisely: the two defects proven by photos are Alex Kim's fault — not there at move-in, found when checking before the subtenant moved in. For Jordan, who sublets in, those two photos exist from his move-in, the Before video was also taken at his move-in, and only the After video is added at move-out. So these records stay with both Alex, who sublet out, and Jordan, who sublet in, and are used in Jordan's settlement. Do you understand this timeline?

→ The demo timeline was fixed: clean move-in → Alex's own two defects → recorded at the sublet hand-off → Jordan's crack → settlement and the deposit dispute.

**#20 · Oct 21**
> There are damage photos at move-in too.

→ A human review step: the user can mark a Detective false alarm "Not damage" with a reason.

**#21 · Oct 21**
> The backend seems fairly complete now, but the frontend is too shabby.
>
> Overall it's too complicated, not well categorized, too much text, hard to read. There should be a summary, and if I want more detail I click and it appears. The Home tab doesn't seem to do anything either. Is it right to show the agent chat there by default? Just put it bottom right like the other tabs and open it on click. I'd like Home to be a more concise, readable dashboard.

→ Full UI redesign: summary tiles and one-line rows that expand, a dashboard Home, a chat button bottom right.

**#22 · Oct 22**
> Bring the server back up.

**#23 · Oct 22**
> Good for now. Is there anything that would make this business richer, add app features, or add fun elements?

**#24 · Oct 22**
> Do what you recommended!

→ Added the move-out precheck ("fix it or pay for it?"), the Deposit Shield score, and the two-minute guided tour.

**#25 · Oct 22**
> Anything else worth trying?

**#26 · Oct 22**
> The photos and videos in @2_Final Project/data are fine, but the PDFs are all my real files. Could you make fake PDFs modeled on their formats? Ideally files with the same values and content we used in the Alex and Jordan example.

→ Eight fictional PDFs in the layout of real renter documents; the demo year was re-run with the real agents. This found and fixed three masking bugs and a stalled gateway call (now a 5-minute limit per call).

## 4. Checking and submitting (Oct 24–25)

**#27 · Oct 24**
> Turn the server on!

**#28 · Oct 24**
> Honestly, if you graded this (by the website criteria I sent you), what score out of 100 would you give?

**#29 · Oct 24**
> Is there a way to raise the quality further before uploading? I want to submit tomorrow. If there's nothing more to do here, I'll do the report and slides, a final check, and upload to GitHub.

→ Fresh-clone dry run (install 2.5 min), privacy and secrets scan of the repository, upper bounds on dependency versions.

**#30 · Oct 25**
> Good — we already have test results, right? Alex and Jordan were already my tests. Can't we write the whole report and slides with those?

→ Report and slides written. Alex and Jordan are fictional, so they are not presented as real users; the real user is the author (real lease, real apartment photos), stated as a limit.

**#31 · Oct 25**
> [pasted: the TA's announcement — Canvas takes only the report HTML, the slides HTML and an optional video; both HTML files must contain the GitHub URL]
>
> Read this carefully and revise the submission.
> It seems the report and slides must contain the GitHub repo URL. And how about making the 3) video too? So we submit these three.
>
> For now just add the URL to the submission files, and it would be great to make a new video. I think an AI grader will grade it and a human grader will review once — if you were the AI grader, what would you grade? The idea matters, of course, but how it was implemented and how complete it is also matter. Is there a way to raise the final quality at this point? The README is friendly enough, right? Would it help to organize the prompts we exchanged about the Final Project and include them?

→ Public repo URL and clone steps added to the report and slides, a demo video, a grader summary in the README, 12 code tests, and this prompts log.
