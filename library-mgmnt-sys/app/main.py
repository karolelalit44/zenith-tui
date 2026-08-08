from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid

app = FastAPI(
    title="Library Management System API",
    description="A comprehensive API for managing books, accounts, and users in a library system",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Book Models
class BookBase(BaseModel):
    title: str
    author: str
    isbn: str
    publisher: str
    year: int
    category: str
    total_copies: int = 1
    available_copies: int = 1

class BookCreate(BookBase):
    pass

class Book(BookBase):
    id: str
    is_deleted: bool = False

    class Config:
        from_attributes = True

# Account Models
class AccountBase(BaseModel):
    username: str
    email: str
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None

class AccountCreate(AccountBase):
    password: str

class Account(AccountBase):
    id: str
    is_active: bool = True
    is_deleted: bool = False
    created_at: str

    class Config:
        from_attributes = True

# User Models
class UserBase(BaseModel):
    username: str
    email: str
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: str
    is_active: bool = True
    is_deleted: bool = False
    created_at: str

    class Config:
        from_attributes = True

# In-memory storage (for demo purposes)
books_db: List[Book] = []
accounts_db: List[Account] = []
users_db: List[User] = []

# Book CRUD Endpoints
@app.post("/books/", response_model=Book)
async def create_book(book: BookCreate):
    book_id = str(uuid.uuid4())
    book_data = Book(
        id=book_id,
        **book.dict()
    )
    books_db.append(book_data)
    return book_data

@app.get("/books/", response_model=List[Book])
async def list_books():
    return [book for book in books_db if not book.is_deleted]

@app.get("/books/{book_id}", response_model=Book)
async def get_book(book_id: str):
    for book in books_db:
        if book.id == book_id and not book.is_deleted:
            return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.put("/books/{book_id}", response_model=Book)
async def update_book(book_id: str, book_update: BookBase):
    for book in books_db:
        if book.id == book_id and not book.is_deleted:
            book.title = book_update.title
            book.author = book_update.author
            book.isbn = book_update.isbn
            book.publisher = book_update.publisher
            book.year = book_update.year
            book.category = book_update.category
            book.total_copies = book_update.total_copies
            book.available_copies = book_update.available_copies
            return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.delete("/books/{book_id}")
async def delete_book(book_id: str):
    for book in books_db:
        if book.id == book_id and not book.is_deleted:
            book.is_deleted = True
            return {"message": "Book deleted successfully"}
    raise HTTPException(status_code=404, detail="Book not found")

# Account CRUD Endpoints
@app.post("/accounts/", response_model=Account)
async def create_account(account: AccountCreate):
    account_id = str(uuid.uuid4())
    account_data = Account(
        id=account_id,
        username=account.username,
        email=account.email,
        full_name=account.full_name,
        phone=account.phone,
        address=account.address,
        is_active=True,
        is_deleted=False,
        created_at="2024-01-01T00:00:00Z"
    )
    accounts_db.append(account_data)
    return account_data

@app.get("/accounts/", response_model=List[Account])
async def list_accounts():
    return [account for account in accounts_db if not account.is_deleted]

@app.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: str):
    for account in accounts_db:
        if account.id == account_id and not account.is_deleted:
            return account
    raise HTTPException(status_code=404, detail="Account not found")

@app.put("/accounts/{account_id}", response_model=Account)
async def update_account(account_id: str, account_update: AccountBase):
    for account in accounts_db:
        if account.id == account_id and not account.is_deleted:
            account.username = account_update.username
            account.email = account_update.email
            account.full_name = account_update.full_name
            account.phone = account_update.phone
            account.address = account_update.address
            return account
    raise HTTPException(status_code=404, detail="Account not found")

@app.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    for account in accounts_db:
        if account.id == account_id and not account.is_deleted:
            account.is_deleted = True
            return {"message": "Account deleted successfully"}
    raise HTTPException(status_code=404, detail="Account not found")

# User CRUD Endpoints
@app.post("/users/", response_model=User)
async def create_user(user: UserCreate):
    user_id = str(uuid.uuid4())
    user_data = User(
        id=user_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        address=user.address,
        is_active=True,
        is_deleted=False,
        created_at="2024-01-01T00:00:00Z"
    )
    users_db.append(user_data)
    return user_data

@app.get("/users/", response_model=List[User])
async def list_users():
    return [user for user in users_db if not user.is_deleted]

@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    for user in users_db:
        if user.id == user_id and not user.is_deleted:
            return user
    raise HTTPException(status_code=404, detail="User not found")

@app.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, user_update: UserBase):
    for user in users_db:
        if user.id == user_id and not user.is_deleted:
            user.username = user_update.username
            user.email = user_update.email
            user.full_name = user_update.full_name
            user.phone = user_update.phone
            user.address = user_update.address
            return user
    raise HTTPException(status_code=404, detail="User not found")

@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    for user in users_db:
        if user.id == user_id and not user.is_deleted:
            user.is_deleted = True
            return {"message": "User deleted successfully"}
    raise HTTPException(status_code=404, detail="User not found")

@app.get("/")
async def root():
    return {
        "message": "Welcome to Library Management System API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }