<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;

class OCRController extends Controller
{

    public function recognizePdfFromS3(Request $request)
    {
        // Validate the incoming request to ensure the file path is provided
        $request->validate([
            'file_path' => 'required|string',
        ]);

        // Retrieve the file path from the request
        $filePath = $request->input('file_path');

        // Generate a temporary signed URL from S3
        $signedUrl = Storage::disk('s3')->temporaryUrl($filePath, now()->addMinutes(15));

        // Make the GET request to the ArchieOCR service using the signed URL
        $response = Http::get('http://localhost:8080/recognize', [
            'file' => $signedUrl,
            'key' => 'your-secret-key', // Replace with your actual key
        ]);

        // Check if the request was successful
        if ($response->successful()) {
            // Return the OCR text from the response
            return response()->json($response->json());
        } else {
            // Handle the error response
            return response()->json([
                'error' => 'Failed to recognize text from PDF.',
                'details' => $response->json(),
            ], $response->status());
        }
    }

    public function recognizePdf(Request $request)
    {
        // Validate the incoming request to ensure a file is provided
        $request->validate([
            'file' => 'required|file|mimes:pdf|max:4096',
        ]);

        // Retrieve the file from the request
        $pdfFile = $request->file('file');

        // Make the POST request to the ArchieOCR service
        $response = Http::attach(
            'file', file_get_contents($pdfFile->getRealPath()), $pdfFile->getClientOriginalName()
        )->post('http://localhost:8080/recognize', [
            'key' => 'your-secret-key', // Replace with your actual key
        ]);

        // Check if the request was successful
        if ($response->successful()) {
            // Return the OCR text from the response
            return response()->json($response->json());
        } else {
            // Handle the error response
            return response()->json([
                'error' => 'Failed to recognize text from PDF.',
                'details' => $response->json(),
            ], $response->status());
        }
    }

}