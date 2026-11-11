# Quality Control Guide — Double Reading, Tie-breakers and Approval

| | |
|---|---|
| **Version** | 0.1 |
| **Date** | 2026-11-11 |
| **For** | Project leads, lab readers, data reviewers |

## 1. Setting up (project lead)

On the project page, click **QC settings**:

- **Readers required**, for each smear type the project uses: *1 reader*, or *2 independent readers (+ tie-breaker if they disagree)*. Many studies double-read thick smears and single-read thin smears.
- **Discordance threshold** (default 50%): how far apart two densities (or parasitaemias) can be before the readers are said to disagree. It's measured as the difference divided by the average of the two readings. At 50%, 1,000 vs 1,400/µL agree (33%), but 1,000 vs 1,800/µL disagree (57%).
- **After a tie-breaker:** either the tie-breaker's reading becomes the final result, or the final result is the majority positive/negative and species, with density the mean of the two closest readings.

Changes apply to slides recorded from then on.

## 2. Reading slides (lab readers)

1. **Reader 1** records the slide from the sample page (**Record smear result**), as before.
2. If the smear type is double-read, the slide shows **Awaiting reader 2**. Another reader opens the slide and clicks **Enter reader 2 result**.
3. **Blind reading:** while a slide is awaiting reader 2 or a tie-breaker, you can't see other readers' results. You only see your own. The same person can't read one slide twice.
4. The system compares the two readings:
   - **They agree:** the slide gets its final result (the mean of the two densities).
   - **They disagree** (positive vs negative, different species, or density too far apart): the slide shows **Awaiting tie-breaker**. A third reader who hasn't read the slide clicks **Enter tie-breaker result**.

Each project's **Review queue** lists slides awaiting reader 2 and awaiting a tie-breaker.

## 3. Approving results (data reviewers)

- Reviewers can see every reading at any time, including why readers disagreed.
- **Review queue → Final results awaiting approval:** tick checked results and click **Approve and lock selected**. Results that needed a tie-breaker are listed last and marked with ⚠; check those individually.
- Or approve one at a time from the slide page with **Approve and lock**.
- A **locked** result can't change: readings and slide details can't be edited.
- To correct a locked result, click **Unlock…** on the slide page and give a reason. The reason is kept in the slide's history. After the correction, the result needs approving again.

Only data reviewers and system admins can approve, lock and unlock. Project leads and readers can't, so the people producing results aren't the ones approving them.

## 4. What everyone sees

| Where | Shows |
|---|---|
| Results list, sample page, review queue | The slide's **final** result, or its status (*Awaiting reader 2*, *Awaiting tie-breaker*). 🔒 = approved and locked. ⚠ = readers disagreed. |
| Slide page | The final result, how it was decided, any disagreement, and each reading (hidden while being read blind) |
| Slide history | Every change to the slide, its readings and its final result, including lock/unlock reasons |
| Dashboard | Counts needing attention across your active projects |
