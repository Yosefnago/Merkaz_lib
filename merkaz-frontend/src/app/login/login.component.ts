
/**
 * LoginComponent
 * -----------------------
 * Handles user authentication.
 * Sends credentials to Flask backend and handles success/failure responses.
 * Backend is expected to respond strictly in JSON format.
 */
import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import {CommonModule} from '@angular/common';

@Component({
  selector: 'app-login',
  standalone: true,
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
  imports: [
    CommonModule,
    FormsModule,
  ]
})
export class LoginComponent {
  /** User email input */
  email = '';

  /** User password input */
  password = '';

  /** Message displayed on successful login */
  message = '';

  /** Error message displayed on failed login */
  error = '';

  showPassword = false

  constructor(private http: HttpClient, private router: Router) {}

  togglePasswordVisibility() {
    this.showPassword = !this.showPassword;
  }

  /**
   * Triggered on form submission.
   * Sends a POST request to Flask endpoint /login with JSON payload.
   * Backend should respond with a JSON object (see API Contract above).
   */
  onSubmit() {
    this.http.post('http://localhost:8000/login', {
      email: this.email,
      password: this.password
    }).subscribe({
      // Expected response example:
        // {
        //   "message": "Login successful",
        //   "email": "user@example.com",
        //   "role": "user",
        //   "token": "jwt-123..."
        // }
      next: (res: any) => {

        this.message = 'Login successful';
        localStorage.setItem('token', res.token);

        // Redirect to dashboard
        this.router.navigate(['/dashboard']);
      },
      error: () => {

        // Expected error response example:
        // { "error": "Invalid credentials" }
        this.error = 'Invalid credentials';
      }
    });
  }
}
