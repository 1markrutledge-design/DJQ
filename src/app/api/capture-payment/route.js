import { NextResponse } from 'next/server';
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

export async function POST(request) {
    try {
        const { paymentIntentId } = await request.json();

        if (!paymentIntentId) {
            return NextResponse.json({ error: 'Missing paymentIntentId' }, { status: 400 });
        }

        // Finalize the payment
        const paymentIntent = await stripe.paymentIntents.capture(paymentIntentId);

        return NextResponse.json({
            success: true,
            status: paymentIntent.status
        });
    } catch (error) {
        console.error('Capture Error:', error);
        return NextResponse.json(
            { error: `Capture Failed: ${error.message}` },
            { status: 500 }
        );
    }
}
