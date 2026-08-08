# Library Management System

A comprehensive FastAPI-based library management system with CRUD APIs for books, accounts, and users.

## Project Structure

```
library-mgmnt-sys/
├── app/
│   └── main.py              # FastAPI application with all CRUD endpoints
├── Dockerfile                # Docker configuration
├── requirements.txt          # Python dependencies
├── README.md                 # This file
└── docker-compose.yml        # Optional: Docker compose configuration
```

## Features

### Book Management
- Create, read, update, and delete books
- Manage book inventory (total and available copies)
- Search and filter books by various criteria
- Soft delete functionality

### Account Management
- Create and manage user accounts
- Account activation/deactivation
- Soft delete functionality

### User Management
- Create and manage system users
- User roles and permissions
- Soft delete functionality

### API Documentation
- Interactive API documentation via Swagger UI
- ReDoc documentation
- RESTful API design

## API Endpoints

### Books
- `GET /books/` - List all books
- `GET /books/{book_id}` - Get book by ID
- `POST /books/` - Create new book
- `PUT /books/{book_id}` - Update book
- `DELETE /books/{book_id}` - Delete book (soft delete)

### Accounts
- `GET /accounts/` - List all accounts
- `GET /accounts/{account_id}` - Get account by ID
- `POST /accounts/` - Create new account
- `PUT /accounts/{account_id}` - Update account
- `DELETE /accounts/{account_id}` - Delete account (soft delete)

### Users
- `GET /users/` - List all users
- `GET /users/{user_id}` - Get user by ID
- `POST /users/` - Create new user
- `PUT /users/{user_id}` - Update user
- `DELETE /users/{user_id}` - Delete user (soft delete)

### System Info
- `GET /` - System status and API info

## Models

### Book
- `title` (str): Book title
- `author` (str): Book author
- `isbn` (str): ISBN number
- `publisher` (str): Publisher name
- `year` (int): Publication year
- `category` (str): Book category
- `total_copies` (int): Total number of copies
- `available_copies` (int): Available copies
- `id` (str): Unique identifier
- `is_deleted` (bool): Deletion status

### Account
- `username` (str): Account username
- `email` (str): Email address
- `full_name` (str): Full name
- `phone` (str, optional): Phone number
- `address` (str, optional): Address
- `id` (str): Unique identifier
- `is_active` (bool): Account status
- `is_deleted` (bool): Deletion status
- `created_at` (str): Creation timestamp

### User
- `username` (str): Username
- `email` (str): Email address
- `full_name` (str): Full name
- `phone` (str, optional): Phone number
- `address` (str, optional): Address
- `id` (str): Unique identifier
- `is_active` (bool): User status
- `is_deleted` (bool): Deletion status
- `created_at` (str): Creation timestamp

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Docker (optional but recommended)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd library-mgmnt-sys
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

#### Option 1: Direct Run

1. Run the FastAPI application:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. Open your browser and navigate to:
   - **API Documentation**: http://localhost:8000/docs
   - **ReDoc**: http://localhost:8000/redoc
   - **API Root**: http://localhost:8000/

#### Option 2: Docker

1. Build the Docker image:
   ```bash
   docker build -t library-mgmnt-sys .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 library-mgmnt-sys
   ```

3. Access the API at: http://localhost:8000

#### Option 3: Docker Compose (Optional)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  library-mgmnt-sys:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PYTHONPATH=/app
    volumes:
      - ./app:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then run:
```bash
docker-compose up -d
```

## API Usage Examples

### Create a Book

```bash
curl -X POST http://localhost:8000/books/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "The Great Gatsby",
    "author": "F. Scott Fitzgerald",
    "isbn": "978-0-7432-7356-5",
    "publisher": "Scribner",
    "year": 1925,
    "category": "Fiction",
    "total_copies": 5,
    "available_copies": 5
  }'
```

### Get All Books

```bash
curl http://localhost:8000/books/
```

### Create an Account

```bash
curl -X POST http://localhost:8000/accounts/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "phone": "+1234567890",
    "address": "123 Main St",
    "password": "securepassword123"
  }'
```

### Create a User

```bash
curl -X POST http://localhost:8000/users/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "jane_smith",
    "email": "jane@example.com",
    "full_name": "Jane Smith",
    "phone": "+1987654321",
    "address": "456 Oak Ave",
    "password": "securepassword456"
  }'
```

## Testing

The application includes basic validation and error handling. You can test the endpoints using:

1. **Swagger UI**: Interactive API documentation
2. **Postman**: Import the OpenAPI specification
3. **curl**: Command-line tool for API testing

## Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Successful request
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid input data
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

## Deployment

### Production Considerations

1. **Database**: The current implementation uses in-memory storage. For production, consider using a persistent database.

2. **Security**: 
   - Use HTTPS in production
   - Implement authentication and authorization
   - Add rate limiting
   - Regular security audits

3. **Performance**:
   - Use a production-ready ASGI server (Gunicorn, uvicorn with workers)
   - Implement caching for frequently accessed data
   - Use load balancing for high traffic

4. **Monitoring**:
   - Implement logging
   - Set up monitoring and alerting
   - Regular backups

### Environment Variables

Create a `.env` file for environment-specific configuration:

```env
# API Configuration
HOST=0.0.0.0
PORT=8000

# CORS Settings
CORS_ORIGINS=http://localhost:3000

# Database (if using persistent storage)
DATABASE_URL=sqlite:///./library.db
```

## License

This project is licensed under the MIT License.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test your changes
5. Submit a pull request

## Acknowledgements

- FastAPI for the excellent web framework
- Pydantic for data validation
- Docker for containerization
- OpenAPI for API documentation