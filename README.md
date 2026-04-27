# Payment Collection AI Agent

A production-ready conversational AI agent that handles end-to-end payment collection, including account lookup, identity verification, balance inquiry, and card payment processing.

## Features

- **State-Driven Conversation**: Predictable and compliant flow control.
- **Robust Verification**: Strict identity checking with multi-factor support and retry limits.
- **Secure Payment Handling**: Luhn-validated card processing with support for partial payments.
- **Deterministic Extraction**: State-aware LLM field extraction to minimize hallucinations.
- **Automatic Evaluation**: Comprehensive test suite covering 12+ real-world scenarios.

## Setup Instructions

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd payment-collection-agent
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables**:
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=your_openai_key_here
    API_BASE_URL=https://se-payment-verification-api.service.external.usea2.aws.prodigaltech.com/openapi
    ```

## Usage

### Interactive CLI
Run the agent in your terminal to test it manually:
```bash
python cli.py
```

### Automated Evaluation
Run the comprehensive evaluation suite to check success rates and scenario metrics:
```bash
python tests/evaluator.py
```

## Sample Conversations

### 1. Successful End-to-End Payment
> **User**: Hi  
> **Agent**: Welcome! Please share your account ID to get started.  
> **User**: My ID is ACC1001  
> **Agent**: Got it. For verification, could you please provide your full name?  
> **User**: Nithin Jain  
> **Agent**: Thanks. Please verify your identity by providing your Date of Birth (YYYY-MM-DD), Aadhaar last 4, or Pincode.  
> **User**: DOB is 1990-05-14  
> **Agent**: Identity verified. Your outstanding balance is ₹1,250.75. How much would you like to pay?  
> **User**: 500  
> **Agent**: Please provide your card number, CVV, and expiry date.  
> **User**: 4532015112830366, CVV 123, Expiry 12/2027  
> **Agent**: Payment successful! Your transaction ID is txn_1762510325322_l1fl4oy. Thank you!

### 2. Verification Failure (Retry Limit)
> **User**: ACC1001  
> **Agent**: Account found. Please provide your full name.  
> **User**: John Doe  
> **Agent**: I'm sorry, those details don't match our records. Please try again.  
> **User**: John Doe  
> **Agent**: Verification failed. You have 1 attempt remaining. Please provide your full name and a secondary factor.  
> **User**: John Doe  
> **Agent**: I'm sorry, I cannot verify your identity at this time. This session has been terminated for security reasons.

### 3. Payment Failure (Invalid Card)
> **User**: [Verified Flow...]  
> **Agent**: Your balance is ₹1,250.75. How much would you like to pay?  
> **User**: 500  
> **Agent**: Please provide your card details.  
> **User**: 1234123412341234, CVV 999, Expiry 01/2020  
> **Agent**: I'm sorry, that card number is invalid and the card has expired. Please provide a valid card.

### 4. Edge Case: Leap Year DOB
> **User**: My ID is ACC1004  
> **Agent**: Account found. Please provide your full name.  
> **User**: Rahul Mehta  
> **Agent**: Thanks. Please provide your DOB or Aadhaar last 4.  
> **User**: 29th Feb 1988  
> **Agent**: Identity verified. Your outstanding balance is ₹3,200.50.
