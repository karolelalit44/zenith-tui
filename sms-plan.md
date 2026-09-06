# School Management System (SMS) - Development Plan

## 1. Project Overview
A robust, multi-role web application designed to manage all aspects of school operations, including academic scheduling, student/teacher management, attendance, examination, and fee collection.

### Technology Stack
* **Backend:** Django (Core Logic & SSR)
* **API Layer:** Django REST Framework (DRF) for mobile readiness and dynamic data.
* **Interactivity:** HTMX (to provide SPA-like feel within Django Templates without heavy JS).
* **Authentication:** SimpleJWT (for stateless API communication) + Django Session Auth (for web interface).
* **Frontend:** Django Templates + Bootstrap 5 (Styling) + Alpine.js (Lightweight client-side state).
* **Database:** PostgreSQL (Recommended for production) or SQLite (for development).

---

## 2. System Architecture: The Hybrid Approach
The system utilizes a hybrid architecture to balance development speed with modern user experience:

1.  **Server-Side Rendering (SSR):** The primary user interface is built using **Django Templates**. This ensures fast initial loads, excellent SEO, and simplified form handling.
2.  **Dynamic Interactivity (HTMX):** Instead of full page reloads, **HTMX** will be used to swap HTML fragments (e.g., updating a single row in an attendance table or submitting a search filter) directly via Django views.
3.  **RESTful API (DRF):** A dedicated API layer provides JSON endpoints. This serves:
    *   Mobile applications (iOS/Android).
    *   Third-party integrations.
    *   Highly complex, state-heavy client-side components if needed.
4.  **Security Bridge:** **JWT (JSON Web Tokens)** will facilitate stateless communication for the API layer, while standard Django sessions handle the web-based template views.

---

## 3. Data Model Design (The Core)

### A. Identity & Access Management
* **Custom User Model:** `id`, `username`, `email`, `password`, `role` (Admin, Teacher, Student, Parent), `is_active`, `created_at`.
* **Profile:** `user` (OneToOne), `phone_number`, `address`, `profile_picture`, `date_of_birth`.

### B. Academic Core
* **AcademicYear:** `year_name` (e.g., 2023-24), `is_current` (Boolean).
* **Classroom:** `name` (e.g., Grade 10), `section` (e.g., A, B), `teacher_in_charge` (FK to Teacher).
* **Subject:** `name`, `subject_code`, `classroom` (FK).
* **Timetable:** `classroom` (FK), `subject` (FK), `teacher` (FK), `day_of_week`, `start_time`, `end_time`.

### C. People Management
* **Student:** `user` (FK to User), `classroom` (FK), `roll_number`, `parent` (FK to User).
* **Teacher:** `user` (FK to User), `specialization`, `joining_date`.

### D. Academic Records
* **Attendance:** `student` (FK), `date`, `status` (Present, Absent, Late), `remarks`.
* **Exam:** `name` (e.g., Midterm), `term`, `date`.
* **Grade/Mark:** `student` (FK), `exam` (FK), `subject` (FK), `marks_obtained`, `total_marks`.

### E. Finance Module
* **FeeStructure:** `classroom` (FK), `fee_type` (Tuition, Library), `amount`.
* **Payment:** `student` (FK), `amount_paid`, `date`, `payment_status` (Paid, Pending), `transaction_id`.

---

## 4. API Specification (DRF)

### Auth & User APIs
* `POST /api/token/` (Login -> Returns Access & Refresh JWT)
* `POST /api/token/refresh/` (Refresh Access Token)
* `GET /api/user/me/` (Current user profile)

### Management APIs
* `GET/POST/PUT/DELETE /api/students/` (Student CRUD)
* `GET/PUT /api/teachers/` (Teacher Management)
* `GET /api/classrooms/` (Classroom Lists)

### Academic & Attendance APIs
* `POST /api/attendance/mark/` (Teacher marks attendance)
* `GET /api/attendance/student/<id>/` (Student attendance history)
* `GET /api/subjects/<id>/` (Subject details)

### Results & Finance APIs
* `POST /api/grades/upload/` (Teacher uploads marks)
* `GET /api/grades/student/<id>/` (Student report card)
* `GET /api/payments/student/<id>/` (Student fee history)

---

## 5. UI/UX Design (Role-Based Dashboards)

### A. Admin Dashboard (The Controller)
* **Overview:** Dashboard with stats (Total Students, Teachers, Revenue).
* **User Management:** Comprehensive tables to Add/Edit/Delete Students, Teachers, and Staff.
* **Academic Setup:** Configuration of Classes, Subjects, and Academic Years.
* **Finance:** Fee settings and collection reports.

### B. Teacher Dashboard (The Instructor)
* **Schedule:** My classes and upcoming timetable.
* **Attendance:** Interactive list of students in their assigned class (using HTMX for quick marking).
* **Marks Entry:** Form-based interface for inputting exam marks.

### C. Student Dashboard (The Learner)
* **Noticeboard:** School announcements and upcoming exams.
* **Academic Progress:** Visual charts of grades and performance.
* **Attendance:** Personal attendance percentage and history.
* **Fees:** View pending/paid status.

### D. Parent Dashboard (The Overseer)
* **Child Profile:** Monitor child's performance and attendance.
* **Fee Portal:** View and simulate fee payments.

---

## 6. Implementation Roadmap

### Phase 1: Foundation & Authentication
1.  Initialize Django Project & environment.
2.  Implement `users` app with **Custom User Model**.
3.  Configure `djangorestframework-simplejwt`.
4.  Build the Login interface (Template for web, API for JWT).

### Phase 2: Database Architecture
1.  Create `school_core` app.
2.  Implement all core models (Academic, People, Records, Finance).
3.  Perform initial migrations and verify via Django Admin.

### Phase 3: Business Logic Development
1.  Implement Attendance logic (Teacher-Classroom assignment validation).
2.  Develop Grade/Marking calculation logic.
3.  Build Fee/Payment processing logic.

### Phase 4: Frontend & API Integration
1.  Develop DRF Serializers and Viewsets.
2.  Build Django Templates using **Bootstrap 5**.
3.  Integrate **HTMX** for dynamic updates (Attendance marking, search filtering, form submissions).
4.  (Optional) Use Axios for any complex JS-heavy components.

### Phase 5: Security, RBAC & Polishing
1.  Implement **Role-Based Access Control (RBAC)** to ensure users only see authorized data.
2.  Add advanced search, filtering, and pagination.
3.  Final UI/UX refinement and performance optimization.
