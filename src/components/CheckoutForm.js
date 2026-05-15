import React, { useEffect, useState } from 'react';
import { PaymentRequestButtonElement, useStripe } from '@stripe/react-stripe-js';

export default function CheckoutForm({ amount, onPaymentSuccess }) {
    const stripe = useStripe();
    const [paymentRequest, setPaymentRequest] = useState(null);

    useEffect(() => {
        if (!stripe) return;

        const pr = stripe.paymentRequest({
            country: 'US',
            currency: 'usd',
            total: {
                label: 'DJ Tip',
                amount: amount * 100, // Stripe expects cents
            },
            requestPayerName: true,
            requestPayerEmail: true,
        });

        // Check if the Payment Request is available (Apple Pay/Google Pay)
        pr.canMakePayment().then((result) => {
            if (result) {
                setPaymentRequest(pr);
            }
        });

        // Listen for payment method creation
        pr.on('paymentmethod', async (ev) => {
            // Create PaymentIntent on the server
            const { clientSecret } = await fetch('/api/create-payment-intent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amount * 100 }),
            }).then((res) => res.json());

            // Confirm the payment
            const { error, paymentIntent } = await stripe.confirmCardPayment(
                clientSecret,
                { payment_method: ev.paymentMethod.id },
                { handleActions: false }
            );

            if (error) {
                // Report to the browser that the payment failed
                ev.complete('fail');
            } else {
                // Report to the browser that the confirmation was successful
                ev.complete('success');
                // With manual capture, the status will be 'requires_capture'
                if (paymentIntent.status === 'succeeded' || paymentIntent.status === 'requires_capture') {
                    onPaymentSuccess(paymentIntent.id);
                }
            }
        });

    }, [stripe, amount, onPaymentSuccess]);

    if (!paymentRequest) {
        // Fallback UI or empty if we only want Apple Pay
        return <div className="text-center text-gray-500 text-sm">Apple Pay not available on this device/browser.</div>;
    }

    return (
        <PaymentRequestButtonElement options={{ paymentRequest }} />
    );
}
