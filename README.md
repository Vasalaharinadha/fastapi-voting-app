# Community Digital Voting System

A FastAPI-based digital voting system that allows communities to create proposals and vote on them. The system ensures secure and transparent voting with features like vote tracking, proposal management, and result calculation.

## Features

- Create, view, and manage voting proposals
- Cast votes with options: yes, no, or abstain
- Automatic proposal expiration based on deadline
- Admin controls for closing proposals
- Vote revocation for active proposals
- Real-time vote counting and results
- Health check endpoint

## API Endpoints

### Proposals

- `POST /proposals/` - Create a new proposal
- `GET /proposals/` - List all proposals
- `GET /proposals/{proposal_id}` - Get details of a specific proposal
- `PATCH /proposals/{proposal_id}/close` - Close a proposal (Admin only)

### Votes

- `POST /proposals/{proposal_id}/vote` - Submit a vote on a proposal
- `DELETE /votes/{vote_id}` - Revoke a vote
- `GET /votes/` - List all votes (for debugging)

### System

- `GET /health` - Health check endpoint

## Data Models

### Proposal
- `id` (int): Unique identifier
- `title` (str): Proposal title
- `description` (str): Detailed description
- `created_at` (datetime): Creation timestamp
- `deadline` (datetime): Voting deadline
- `status` (str): One of 'active', 'closed', or 'expired'
- `yes_count` (int): Number of 'yes' votes
- `no_count` (int): Number of 'no' votes
- `abstain_count` (int): Number of 'abstain' votes

### Vote
- `id` (int): Unique identifier
- `proposal_id` (int): Reference to the proposal
- `voter_name` (str): Name of the voter
- `vote` (str): One of 'yes', 'no', or 'abstain'
- `voted_at` (datetime): Timestamp of the vote

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install fastapi uvicorn sqlite3 pydantic
   ```
3. Run the application:
   ```bash
   uvicorn app:app --reload
   ```

The API will be available at `http://localhost:8000`

## Usage Examples

### Create a Proposal
```bash
curl -X POST "http://localhost:8000/proposals/" \
  -H "Content-Type: application/json" \
  -d '{"title":"New Community Garden", "description":"Proposal to create a community garden in the park", "days_open": 5}'
```

### Cast a Vote
```bash
curl -X POST "http://localhost:8000/proposals/1/vote" \
  -H "Content-Type: application/json" \
  -d '{"voter_name":"alice", "vote":"yes"}'
```

### Close a Proposal (Admin)
```bash
curl -X PATCH "http://localhost:8000/proposals/1/close" \
  -H "X-Admin-Token: secret-admin-token"
```

## Security Notes

- The admin token is currently hardcoded as "secret-admin-token"
- In production, use environment variables for sensitive information
- Consider implementing rate limiting and authentication
- Use HTTPS in production

## License

MIT
