import { NextResponse } from 'next/server';
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

export async function POST(request) {
    try {
        const { paymentIntentId } = await request.json();

        if (!paymentIntentId) {
            return NextResponse.json({ error: 'Missing paymentIntentId' }, { status: 400 });
        }

        // Release the hold (Cancel the authorization)
        // Note: You can't "cancel" if it's already captured, 
        // but for authorizations, cancel releases the funds.
        const paymentIntent = await stripe.paymentIntents.cancel(paymentIntentId);

        return NextResponse.json({
            success: true,
            status: paymentIntent.status
        });
    } catch (error) {
        console.error('Cancel Error:', error);
        return NextResponse.json(
            { error: `Cancel Failed: ${error.message}` },
            { status: 500 }
        );
    }
}
