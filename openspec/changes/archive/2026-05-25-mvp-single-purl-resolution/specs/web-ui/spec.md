## ADDED Requirements

### Requirement: Display resolution form
The system SHALL serve a single HTML page at the root URL with a form for PURL input.

#### Scenario: HTML page loads at root
- **WHEN** user navigates to `GET /`
- **THEN** system returns HTML page with HTTP 200 containing a text input field labeled for PURL entry and a submit button

### Requirement: Display resolution result
The HTML page SHALL fetch the resolution result via the API and display it in a readable card format.

#### Scenario: Successful result shown in card
- **WHEN** user enters a valid PURL and clicks submit
- **THEN** the page SHALL display a result card showing: repository URL as a clickable link, confidence badge, and a "Show details" toggle revealing evidence, warnings, repository type, repository kind, and version reference

#### Scenario: Error state displayed
- **WHEN** the API returns an error (400, 502, or network failure)
- **THEN** the page SHALL display an error message in the result area without redirecting or reloading the page

#### Scenario: Unresolved PURL displayed
- **WHEN** the API returns `repository_url: null` with warnings
- **THEN** the page SHALL display the warning message in the result area

#### Scenario: Loading state shown during request
- **WHEN** user clicks submit and the API request is in flight
- **THEN** the page SHALL show a loading indicator and disable the submit button to prevent duplicate requests