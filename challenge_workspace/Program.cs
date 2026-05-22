// Polyglot Challenge - C#
using System;

public class DiscountCalculator
{
    private string memberId;

    public DiscountCalculator(string memberId)
    {
        this.memberId = memberId;
    }

    public double GetDiscount(double amount)
    {
        if (amount > 100)
        {
            return amount * 0.15;
        }
        else
        {
            return amount * 0.05;
        }
    }
}

class Program
{
    static void Main()
    {
        var calculator = new DiscountCalculator("user_123");
        Console.WriteLine(calculator.GetDiscount(150.0));
    }
}
