# Inline benefit and deduction titles

On an employee's salary page, **Add benefit** and **Add deduction** work even if no company types have been configured. The title field suggests existing active company titles and also accepts a new title. Enter the amount and schedule and save as usual.

A new title creates a reusable type for that employee's company as part of the same database transaction as the employee's item. It does not assign the item to other employees. Matching titles are reused without case-sensitive duplicates. Existing inactive types cannot be bypassed by typing their name. Changing one employee's title selects/creates a different type; it does not rename a shared type used by others.

For a new deduction title, choose Personal or Company scheme. Existing types retain their category. Statutory deduction calculations remain separate.

Tenant and platform employee benefit/deduction POST/PATCH endpoints accept either the existing type ID or `title`, exclusively. Deduction title requests also accept `category` (default `PERSONAL`). No new database migration is needed.
